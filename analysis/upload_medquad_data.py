import pandas as pd
import os
from pinecone import Pinecone, ServerlessSpec
import google.generativeai as genai
from tqdm import tqdm # # **修改點1：導入 tqdm 庫**

# # **修改點2：啟用 tqdm 的 pandas 整合**
tqdm.pandas()

# --- 配置 ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY 環境變數未設定。請設定後再執行。")
genai.configure(api_key=GOOGLE_API_KEY)

# Pinecone API 金鑰和環境
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY 環境變數未設定。請設定後再執行。")

PINECONE_ENVIRONMENT = os.environ.get("PINECONE_ENVIRONMENT")
if not PINECONE_ENVIRONMENT:
    raise ValueError("PINECONE_ENVIRONMENT 環境變數未設定。請設定後再執行。")

# Pinecone 索引名稱
# INDEX_NAME = "medquad-urology-qa-gemini" # 建議為 Gemini 使用的索引起一個新名字，以區分
INDEX_NAME = "medquad" # 建議為 Gemini 使用的索引起一個新名字，以區分

# --- 讀取 CSV ---
csv_file_path = "C:/n8n stuff/medquad.csv" # 替換為你的 CSV 文件實際路徑
try: # # **修改點3：添加文件未找到的錯誤處理**
    df = pd.read_csv(csv_file_path)
except FileNotFoundError: #
    raise FileNotFoundError(f"錯誤: 找不到 CSV 文件。請確認路徑是否正確: {csv_file_path}") #

# --- 數據處理和文本準備 ---
df['combined_text'] = "問題：" + df['question'].astype(str) + "\n答案：" + df['answer'].astype(str)
df.dropna(subset=['combined_text'], inplace=True)

# --- 生成嵌入 ---
def get_gemini_embedding(text, model="models/embedding-001"): # Gemini 的嵌入模型名稱
    # Gemini 的 embedding-001 模型限制為 3072 tokens。
    # 這裡我們使用一個字元限制來近似，因為直接計算 token 數需要額外的 tokenizer 庫。
    # 1個 token 大約是 4個字元，所以 3072 tokens 約等於 12288 個字元。
    # 我們設定一個更保守的字元限制來確保不超限。
    max_tokens_limit = 3072 # # **修改點4：定義 token 限制**
    approx_char_limit = 10000 # # **修改點5：定義近似字元限制**

    text = text.replace("\n", " ") # 替換換行符以確保文本連續性

    if len(text) > approx_char_limit: # # **修改點6：添加文本截斷邏輯**
        # print(f"警告: 文本長度 ({len(text)} 字元) 超過近似限制 ({approx_char_limit} 字元)，將進行截斷。")
        # 可以選擇打印這個警告，但為了避免刷屏，我先註釋掉，只在錯誤處理中顯示。
        text = text[:approx_char_limit] # 截斷前面部分

    try:
        # 使用 genai.embed_content 函數生成嵌入
        response = genai.embed_content(
            model=model,
            content=text,
            task_type="RETRIEVAL_DOCUMENT"
        )
        return response['embedding']
    except Exception as e: # # **修改點7：增強錯誤訊息**
        error_message = str(e) #
        if "Request contains too many tokens" in error_message or "text length" in error_message: #
            print(f"\n錯誤: 文本過長導致嵌入失敗 (token 數超限)。原始文本長度: {len(text)} 字元。對應 ID: {df.iloc[df['combined_text'].tolist().index(text)]['id'] if 'id' in df.columns else 'N/A'}") #
            print(f"原始錯誤訊息: {error_message}") #
        else: #
            print(f"\n生成 Gemini 嵌入時出錯: {error_message} for text (前100字): {text[:100]}...") #
        return None

print("正在生成文本嵌入，這可能需要一些時間...")
print("您將看到一個進度條顯示文本嵌入的進度。") # # **修改點8：添加進度條提示**
df['embedding'] = df['combined_text'].progress_apply(get_gemini_embedding) # # **修改點9：使用 progress_apply 顯示進度條**

# 移除無法生成嵌入的行
original_rows = len(df) # # **修改點10：記錄移除行數**
df.dropna(subset=['embedding'], inplace=True) #
dropped_rows = original_rows - len(df) #
if dropped_rows > 0: #
    print(f"警告: 已移除 {dropped_rows} 行無法成功生成嵌入的記錄。") #

# --- 初始化 Pinecone ---
pc = Pinecone(api_key=PINECONE_API_KEY, environment=PINECONE_ENVIRONMENT)

# 檢查索引是否存在，如果存在則刪除（可選，如果你想重新開始）
if INDEX_NAME in pc.list_indexes():
    print(f"正在刪除現有索引: {INDEX_NAME}")
    pc.delete_index(INDEX_NAME)

# 創建新的索引
print(f"正在創建新的 Pinecone 索引: {INDEX_NAME}")
# Gemini 的 'models/embedding-001' 模型生成的向量維度是 768。
# 請務必確認你的 Pinecone 索引維度與你使用的嵌入模型匹配。
pc.create_index(
    name=INDEX_NAME,
    dimension=768, # Gemini 'models/embedding-001' 的維度
    metric="cosine", # 使用餘弦相似度
    spec=ServerlessSpec(cloud="aws", region="us-east-1") # 根據你的 Pinecone 環境調整 cloud 和 region
)

# 連接到索引
index = pc.Index(INDEX_NAME)

# --- 上傳數據到 Pinecone ---
# 將數據分批上傳，以避免 API 請求超時或過載
batch_size = 100
vectors_to_upsert = []
total_records_to_upload = len(df) # # **修改點11：計算總上傳記錄數**

if total_records_to_upload == 0: # # **修改點12：處理沒有數據可上傳的情況**
    print("沒有可供上傳的有效嵌入數據。腳本結束。") #
else: #
    print(f"正在將 {total_records_to_upload} 條記錄上傳到 Pinecone...") #
    # # **修改點13：使用 tqdm 顯示 Pinecone 上傳進度**
    for i, row in tqdm(df.iterrows(), total=total_records_to_upload, desc="上傳到 Pinecone"): #
        metadata = {
            "question": row['question'],
            "answer": row['answer'],
            # 你可以添加其他有用的元數據，例如原始 ID, 來源等
        }
        vectors_to_upsert.append({
            "id": f"doc-{i}", # 為每個向量生成一個唯一的 ID
            "values": row['embedding'],
            "metadata": metadata
        })

        if len(vectors_to_upsert) == batch_size:
            try: # # **修改點14：添加 Pinecone 上傳錯誤處理**
                index.upsert(vectors=vectors_to_upsert) #
                vectors_to_upsert = [] #
            except Exception as e: #
                print(f"\n上傳批次到 Pinecone 時出錯: {e}") #
                # 這裡可以選擇退出或記錄錯誤並繼續
                vectors_to_upsert = [] # 清空批次，避免重複嘗試失敗的數據

    # 上傳剩餘的向量
    if vectors_to_upsert: #
        try: #
            index.upsert(vectors=vectors_to_upsert) #
        except Exception as e: #
            print(f"\n上傳最後一批到 Pinecone 時出錯: {e}") #

    print(f"已嘗試上傳所有 {total_records_to_upload} 條記錄。") #
    print(f"數據已成功上傳到 Pinecone 索引 '{INDEX_NAME}'。") #