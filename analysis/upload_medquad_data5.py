import pandas as pd
import os
from pinecone import Pinecone, ServerlessSpec
import google.generativeai as genai
from tqdm import tqdm
import time
import random

# 啟用 tqdm 顯示進度條
tqdm.pandas()

# --- 1. 配置與路徑設定 ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.environ.get("PINECONE_ENVIRONMENT")

# === 關鍵修改：使用絕對路徑，確保檔案存取位置正確 ===
CSV_FILE_PATH = "C:/n8n stuff/medquad.csv"
EMBEDDING_BACKUP_FILE = "C:/n8n stuff/medquad_with_embeddings_backup.pkl" 
# =================================================

# 檢查 API Key
if not all([GOOGLE_API_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT]):
    raise ValueError("請確認所有環境變數 (GOOGLE_API_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT) 皆已設定。")

genai.configure(api_key=GOOGLE_API_KEY)

# Pinecone 設定
INDEX_NAME = "medquad-gemini-embedding-001"
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSION = 3072

# --- 2. 輔助函式 ---

def get_embedding_with_retry(text, retries=3, delay=2):
    """
    嘗試生成嵌入，如果失敗則重試。包含字數限制防止 API 報錯。
    """
    approx_char_limit = 9000 # Gemini 限制 token，這裡用字元數做安全限制
    text = str(text).replace("\n", " ") # 轉為字串並移除換行
    
    if len(text) > approx_char_limit:
        text = text[:approx_char_limit]

    for attempt in range(retries + 1):
        try:
            response = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type="RETRIEVAL_DOCUMENT"
            )
            time.sleep(1.0) # 稍微休息避免 Rate Limit
            return response['embedding']
            
        except Exception as e:
            if attempt < retries:
                # 指數退避
                sleep_time = (delay * (2 ** attempt)) + random.uniform(0, 1)
                # print(f"生成失敗，{sleep_time:.2f} 秒後重試...") # 減少 log 雜訊
                time.sleep(sleep_time)
            else:
                # 重試次數用盡，真的失敗了
                print(f"\n❌ Embedding 生成最終失敗: {text[:30]}... 原因: {e}")
                return None

def upsert_batch_with_retry(index, vectors, retries=5, delay=2):
    """
    上傳向量批次至 Pinecone，失敗自動重試。
    """
    for attempt in range(retries + 1):
        try:
            index.upsert(vectors=vectors)
            return True
        except Exception as e:
            if attempt < retries:
                sleep_time = (delay * (2 ** attempt)) + random.uniform(0, 1)
                print(f"\n⚠️ Pinecone 上傳失敗，{sleep_time:.2f} 秒後重試 ({attempt+1}/{retries})...")
                time.sleep(sleep_time)
            else:
                print(f"\n❌ Pinecone 上傳最終失敗: {e}")
                return False

# --- 3. 主流程邏輯 ---

def main():
    # === 步驟 A: 獲取資料 (優先讀取備份檔) ===
    
    if os.path.exists(EMBEDDING_BACKUP_FILE):
        print(f"📂 發現已存在的嵌入備份檔案：{EMBEDDING_BACKUP_FILE}")
        print("🚀 直接讀取檔案，跳過 Gemini API 生成步驟...")
        df = pd.read_pickle(EMBEDDING_BACKUP_FILE)
        print(f"✅ 成功載入 {len(df)} 筆資料")
    else:
        print(f"⚠️ 未發現備份檔案 ({EMBEDDING_BACKUP_FILE})")
        print("📥 開始讀取原始 CSV 並調用 API 生成嵌入...")
        
        # 1. 讀取 CSV
        if not os.path.exists(CSV_FILE_PATH):
            raise FileNotFoundError(f"找不到原始 CSV 檔案: {CSV_FILE_PATH}")
            
        df = pd.read_csv(CSV_FILE_PATH)
        print(f"原始資料共 {len(df)} 筆")

        # 2. 資料前處理
        df['combined_text'] = "問題：" + df['question'].astype(str) + "\n答案：" + df['answer'].astype(str)
        df.dropna(subset=['combined_text'], inplace=True)

        # 3. 生成嵌入 (最花時間的步驟)
        print("🚀 開始生成嵌入 (這可能需要一段時間)...")
        df['embedding'] = df['combined_text'].progress_apply(get_embedding_with_retry)

        # 4. 移除生成失敗的資料
        failed_count = df['embedding'].isnull().sum()
        if failed_count > 0:
            print(f"❌ 移除 {failed_count} 筆生成失敗的資料")
            df.dropna(subset=['embedding'], inplace=True)
        
        # 5. *** 關鍵存檔 ***
        print(f"💾 正在將帶有嵌入的資料保存至: {EMBEDDING_BACKUP_FILE}")
        df.to_pickle(EMBEDDING_BACKUP_FILE)
        print("✅ 存檔完成！下次執行將直接讀取此檔，無需重新付費/等待生成。")

    # === 步驟 B: 上傳至 Pinecone ===

    print(f"準備上傳有效資料共 {len(df)} 筆")

    pc = Pinecone(api_key=PINECONE_API_KEY)

    # 檢查並重建索引 (確保環境乾淨)
    existing_indexes = [i.name for i in pc.list_indexes()]
    if INDEX_NAME in existing_indexes:
        print(f"發現舊索引 {INDEX_NAME}，正在刪除以確保資料一致性...")
        pc.delete_index(INDEX_NAME)
        time.sleep(15) # 等待刪除完成

    print("正在建立新索引...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=EMBEDDING_DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
    
    # 等待索引初始化
    time.sleep(5) 
    index = pc.Index(INDEX_NAME)

    # 批次上傳
    batch_size = 100
    vectors_buffer = []
    upload_success_count = 0

    print("🚀 開始上傳至 Pinecone...")
    
    # 為了防止 Metadata 過大導致錯誤，這裡做簡單截斷 (Pinecone 限制 metadata 單筆 40KB)
    META_TEXT_LIMIT = 30000 

    for i, row in tqdm(df.iterrows(), total=len(df), desc="上傳進度"):
        # 處理 Metadata，避免過長
        q_text = str(row['question'])
        a_text = str(row['answer'])
        
        # 簡單截斷防止 40KB 錯誤
        if len(a_text) > META_TEXT_LIMIT:
            a_text = a_text[:META_TEXT_LIMIT] + "...(truncated)"

        metadata = {
            "question": q_text,
            "answer": a_text
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

    # 上傳剩餘的
    if vectors_buffer:
        if upsert_batch_with_retry(index, vectors_buffer):
            upload_success_count += len(vectors_buffer)

    # === 步驟 C: 最終核對 ===
    print("\n========== 最終核對報告 ==========")
    print(f"本地準備上傳筆數: {len(df)}")
    print(f"成功上傳筆數: {upload_success_count}")

    print("等待 Pinecone 更新統計數據 (約需 10-20 秒)...")
    time.sleep(15)
    
    stats = index.describe_index_stats()
    print(f"Pinecone 雲端實際筆數: {stats.total_vector_count}")

    if stats.total_vector_count >= upload_success_count:
        print("✅ 資料完整性確認成功！所有資料已上傳。")
    else:
        print("⚠️ 雲端數量少於預期，請檢查錯誤日誌。")

if __name__ == "__main__":
    main()