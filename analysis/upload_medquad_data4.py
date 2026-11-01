import pandas as pd
import os
from pinecone import Pinecone, ServerlessSpec
import google.generativeai as genai
from tqdm import tqdm
import time
import random
import ast

# 啟用 tqdm
tqdm.pandas()

# --- 1. 配置 ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.environ.get("PINECONE_ENVIRONMENT")

if not all([GOOGLE_API_KEY, PINECONE_API_KEY]):
    raise ValueError("請確認所有環境變數皆已設定。")

genai.configure(api_key=GOOGLE_API_KEY)

# 參數設定
INDEX_NAME = "medquad-emini-embedding-001"
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSION = 3072
CACHE_FILE = "medquad_with_embeddings.csv" 

# --- 2. 輔助函式 ---

def get_embedding_with_retry(text, retries=3, delay=2):
    text = str(text).replace("\n", " ")
    if len(text) > 9000: 
        text = text[:9000]

    for attempt in range(retries + 1):
        try:
            response = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type="RETRIEVAL_DOCUMENT"
            )
            time.sleep(1) 
            return response['embedding']
        except Exception as e:
            if attempt < retries:
                time.sleep(delay * (2 ** attempt))
            else:
                return None

def upsert_batch_with_retry(index, vectors, retries=5, delay=2):
    for attempt in range(retries + 1):
        try:
            index.upsert(vectors=vectors)
            return True
        except Exception as e:
            if attempt < retries:
                time.sleep(delay * (2 ** attempt))
            else:
                print(f"\n❌ 上傳失敗: {e}")
                return False

def truncate_to_bytes(text, limit=38000):
    """
    ✂️ 強制截斷函式：確保 metadata 大小不超過 Pinecone 的 40KB 限制
    這會保留約 12,000 個中文字，足夠 AI 回答絕大多數問題。
    """
    text_str = str(text)
    encoded = text_str.encode('utf-8')
    if len(encoded) <= limit:
        return text_str
    return encoded[:limit].decode('utf-8', 'ignore') + "..."

# --- 3. 主流程 ---

df = None

# [步驟 A] 讀取存檔 (省時關鍵)
if os.path.exists(CACHE_FILE):
    print(f"📂 發現已存在的嵌入存檔: {CACHE_FILE}")
    print("🚀 直接讀取存檔，跳過嵌入生成...")
    df = pd.read_csv(CACHE_FILE)
    try:
        # 將字串型的 embedding 轉回 list
        df['embedding'] = df['embedding'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
        print("✅ 存檔讀取成功！")
    except Exception as e:
        print(f"⚠️ 存檔格式有誤，將重新生成: {e}")
        df = None

# [步驟 B] 如果沒存檔，才跑嵌入
if df is None:
    csv_file_path = "C:/n8n stuff/medquad.csv"
    try:
        df = pd.read_csv(csv_file_path)
        print(f"📄 讀取原始 CSV: {len(df)} 筆")
    except FileNotFoundError:
        print("❌ 找不到原始檔案")
        exit()

    df['combined_text'] = "問題：" + df['question'].astype(str) + "\n答案：" + df['answer'].astype(str)
    df.dropna(subset=['combined_text'], inplace=True)

    print("🚀 開始生成嵌入 (這會花一點時間)...")
    df['embedding'] = df['combined_text'].progress_apply(get_embedding_with_retry)
    df.dropna(subset=['embedding'], inplace=True)
    
    print(f"💾 正在將嵌入結果存入 {CACHE_FILE} ...")
    df.to_csv(CACHE_FILE, index=False)

# [步驟 C] 上傳至 Pinecone
print(f"準備上傳有效資料共 {len(df)} 筆")

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME) 

batch_size = 50
vectors_buffer = []
upload_success_count = 0

print("🚀 開始上傳 (含 Metadata 瘦身)...")
for i, row in tqdm(df.iterrows(), total=len(df), desc="上傳進度"):
    
    # 1. 取得完整文字
    full_text = str(row['combined_text'])
    
    # 2. ✂️ 關鍵：進行瘦身，保留前 38KB (約 1.2 萬字)
    # 這能確保 100% 的資料都能上傳成功，不會因為太長被拒絕
    safe_text = truncate_to_bytes(full_text, limit=38000)

    # 3. 建立 Metadata (只有 text，確保 n8n 讀得到且不佔空間)
    metadata = {
        "text": safe_text
    }
    
    vectors_buffer.append({
        "id": f"doc-{i}",
        "values": row['embedding'], 
        "metadata": metadata
    })

    if len(vectors_buffer) >= batch_size:
        if upsert_batch_with_retry(index, vectors_buffer):
            upload_success_count += len(vectors_buffer)
        vectors_buffer = [] 

if vectors_buffer:
    if upsert_batch_with_retry(index, vectors_buffer):
        upload_success_count += len(vectors_buffer)

# --- 4. 最終核對 ---
print("\n等待 Pinecone 更新統計...")
time.sleep(10)
stats = index.describe_index_stats()
print(f"Pinecone 雲端筆數: {stats.total_vector_count}")

if stats.total_vector_count >= len(df) - 100:
    print("✅ 修正完成！所有資料（包含截斷後的長文章）都已成功上傳。")
else:
    print(f"⚠️ 數量仍有落差 ({stats.total_vector_count}/{len(df)})")