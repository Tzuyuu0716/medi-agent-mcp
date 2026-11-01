import pandas as pd
import os
from pinecone import Pinecone, ServerlessSpec
import google.generativeai as genai
from tqdm import tqdm
import time
import random # 用於隨機退避時間

# 啟用 tqdm
tqdm.pandas()

# --- 1. 配置 ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.environ.get("PINECONE_ENVIRONMENT")

if not all([GOOGLE_API_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT]):
    raise ValueError("請確認所有環境變數 (GOOGLE_API_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT) 皆已設定。")

genai.configure(api_key=GOOGLE_API_KEY)

# 設定參數
INDEX_NAME = "medquad-gemini-embed004"
EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_DIMENSION = 768

# --- 2. 輔助函式：帶有重試機制的 API 呼叫 ---

def get_embedding_with_retry(text, retries=3, delay=2):
    """
    嘗試生成嵌入，如果失敗則重試。
    retries: 重試次數
    delay: 初始等待秒數
    """
    approx_char_limit = 8000
    text = text.replace("\n", " ")
    if len(text) > approx_char_limit:
        text = text[:approx_char_limit]

    for attempt in range(retries + 1):
        try:
            response = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type="RETRIEVAL_DOCUMENT"
            )
            # 成功後稍微休息，避免觸發速率限制
            time.sleep(1.5) 
            return response['embedding']
            
        except Exception as e:
            if attempt < retries:
                # 指數退避: 每次失敗等待時間加倍 (2s -> 4s -> 8s) + 隨機抖動
                sleep_time = (delay * (2 ** attempt)) + random.uniform(0, 1)
                print(f"\n⚠️ Embedding 生成失敗，{sleep_time:.2f} 秒後重試 ({attempt+1}/{retries})... 錯誤: {e}")
                time.sleep(sleep_time)
            else:
                # 重試次數用盡，真的失敗了
                print(f"\n❌ Embedding 生成最終失敗: {text[:30]}... 原因: {e}")
                return None

def upsert_batch_with_retry(index, vectors, retries=5, delay=2):
    """
    上傳向量批次，如果失敗則重試。
    """
    for attempt in range(retries + 1):
        try:
            index.upsert(vectors=vectors)
            return True # 成功
        except Exception as e:
            if attempt < retries:
                sleep_time = (delay * (2 ** attempt)) + random.uniform(0, 1)
                print(f"\n⚠️ Pinecone 上傳失敗，{sleep_time:.2f} 秒後重試 ({attempt+1}/{retries})...")
                time.sleep(sleep_time)
            else:
                print(f"\n❌ Pinecone 上傳最終失敗 (批次丟失): {e}")
                return False

# --- 3. 主流程 ---

# 讀取 CSV
csv_file_path = "C:/n8n stuff/medquad.csv"
df = pd.read_csv(csv_file_path)
print(f"原始資料共 {len(df)} 筆")

# 資料處理
df['combined_text'] = "問題：" + df['question'].astype(str) + "\n答案：" + df['answer'].astype(str)
df.dropna(subset=['combined_text'], inplace=True)

# 生成嵌入 (使用重試機制)
print("🚀 開始生成嵌入 (含自動重試機制)...")
df['embedding'] = df['combined_text'].progress_apply(get_embedding_with_retry)

# 檢查失敗筆數
failed_embeddings = df[df['embedding'].isnull()]
if not failed_embeddings.empty:
    print(f"❌ 警告：共有 {len(failed_embeddings)} 筆資料無法生成嵌入，將被移除。")
    # 可選：將失敗的資料存檔檢查
    # failed_embeddings.to_csv("failed_embeddings.csv", index=False)
    
df.dropna(subset=['embedding'], inplace=True)
print(f"準備上傳有效資料共 {len(df)} 筆")

# 初始化 Pinecone
pc = Pinecone(api_key=PINECONE_API_KEY)

# 重建索引
if INDEX_NAME in [i.name for i in pc.list_indexes()]:
    pc.delete_index(INDEX_NAME)
    time.sleep(5)

pc.create_index(
    name=INDEX_NAME,
    dimension=EMBEDDING_DIMENSION,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)
index = pc.Index(INDEX_NAME)

# 上傳數據
batch_size = 100
vectors_buffer = []
upload_success_count = 0

print("🚀 開始上傳至 Pinecone...")
for i, row in tqdm(df.iterrows(), total=len(df), desc="上傳進度"):
    metadata = {
        "question": str(row['question']),
        "answer": str(row['answer'])
    }
    
    vectors_buffer.append({
        "id": f"doc-{i}",
        "values": row['embedding'],
        "metadata": metadata
    })

    if len(vectors_buffer) >= batch_size:
        if upsert_batch_with_retry(index, vectors_buffer):
            upload_success_count += len(vectors_buffer)
        vectors_buffer = [] # 清空

# 上傳最後一批
if vectors_buffer:
    if upsert_batch_with_retry(index, vectors_buffer):
        upload_success_count += len(vectors_buffer)

# --- 4. 最終核對 (Verification) ---
print("\n========== 最終核對報告 ==========")
print(f"預計上傳筆數: {len(df)}")
print(f"成功上傳筆數: {upload_success_count}")

# 呼叫 Pinecone 統計數據 (注意：Pinecone 更新統計數據可能有幾秒延遲)
time.sleep(5) 
stats = index.describe_index_stats()
print(f"Pinecone 雲端實際筆數 (total_vector_count): {stats.total_vector_count}")

if stats.total_vector_count == len(df):
    print("✅ 完美！資料完整性 100% 確認。")
else:
    print("⚠️ 注意：本地計數與雲端計數不符，請檢查是否有批次上傳失敗。")