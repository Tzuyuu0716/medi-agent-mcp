import pandas as pd

# # --- 設定檔案路徑 ---
# csv_file_path = "C:/n8n stuff/medquad.csv"

# # --- 讀取 CSV 並處理錯誤 ---
# try:
#     df = pd.read_csv(csv_file_path)
    
#     # --- 檢查 'focus_area' 欄位是否存在 ---
#     if 'focus_area' in df.columns:
#         # --- 篩選並印出不重複的 focus_area 種類 ---
#         focus_areas = df['focus_area'].unique()
#         print("所有不重複的 focus_area 種類如下:")
#         for area in focus_areas:
#             print(f"- {area}")
            
#     else:
#         print("錯誤: 在 CSV 檔案中找不到 'focus_area' 欄位。")
        
# except FileNotFoundError:
#     print(f"錯誤: 找不到 CSV 文件。請確認路徑是否正確: {csv_file_path}")
# except Exception as e:
#     print(f"發生其他錯誤: {e}")

# --- 設定檔案路徑 ---
csv_file_path = "C:/n8n stuff/medquad.csv"
output_csv_file_path = "C:/n8n stuff/medquad_blood.csv"

# --- 讀取 CSV 並處理錯誤 ---
try:
    df = pd.read_csv(csv_file_path)
    
    # --- 檢查 'focus_area' 欄位是否存在 ---
    if 'focus_area' in df.columns:
        # --- 篩選出 focus_area 包含 'blood' 的資料 ---
        # 注意：使用 .str.contains() 來進行字串部分匹配，`na=False` 確保 NaN 值不會被包含
        blood_related_df = df[df['focus_area'].str.contains('blood', case=False, na=False)]
        
        # --- 檢查是否有篩選出任何資料 ---
        if not blood_related_df.empty:
            # --- 將篩選結果存為新的 CSV 檔案 ---
            blood_related_df.to_csv(output_csv_file_path, index=False)
            print(f"已成功將包含 'blood' 的資料儲存到: {output_csv_file_path}")
        else:
            print("找不到任何 'focus_area' 包含 'blood' 的資料。")

    else:
        print("錯誤: 在 CSV 檔案中找不到 'focus_area' 欄位。")
        
except FileNotFoundError:
    print(f"錯誤: 找不到 CSV 文件。請確認路徑是否正確: {csv_file_path}")
except Exception as e:
    print(f"發生其他錯誤: {e}")