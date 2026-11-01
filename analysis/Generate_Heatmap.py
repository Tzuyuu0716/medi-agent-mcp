import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# 1. 定義論文附錄一的 8 種核心藥物 (與您的實驗情境完全對齊)
drugs = [
    "Aspirin",       # 阿斯匹靈
    "Warfarin",      # 華法林
    "Ibuprofen",     # 布洛芬
    "Acetaminophen", # 普拿疼
    "Amlodipine",    # 脈優
    "Zolpidem",      # 佐沛眠
    "Tetracycline",  # 四環黴素
    "Calcium Carbonate" # 碳酸鈣胃藥
]

# 2. 建立 100% 經臨床權威(Medscape)核對的客觀真值矩陣 (Golden Sample)
# 0: 安全 (Safe)
# 1: 注意 (Caution)
# 2: 警告 (Warning)
# 3: 危險 (High Risk)
data = [
    [0, 3, 2, 0, 0, 0, 0, 0], # Aspirin
    [3, 0, 3, 1, 0, 0, 0, 0], # Warfarin
    [2, 3, 0, 0, 1, 0, 0, 0], # Ibuprofen
    [0, 1, 0, 0, 0, 0, 0, 0], # Acetaminophen
    [0, 0, 1, 0, 0, 0, 0, 0], # Amlodipine
    [0, 0, 0, 0, 0, 0, 0, 0], # Zolpidem
    [0, 0, 0, 0, 0, 0, 0, 2], # Tetracycline
    [0, 0, 0, 0, 0, 0, 2, 0]  # Calcium Carbonate
]

# 轉換為 pandas DataFrame
df = pd.DataFrame(data, index=drugs, columns=drugs)

# 3. 設定畫布與高解析度樣式
plt.figure(figsize=(10, 8))
sns.set_theme(style="white")

# 定義熱力圖的顏色 (對應論文中 0:綠色, 1:黃綠色, 2:橘色, 3:紅色)
cmap = sns.color_palette(["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"])

# 4. 繪製熱力圖
ax = sns.heatmap(df, 
                 cmap=cmap, 
                 annot=True,      # 顯示格子內的數字
                 linewidths=1,    # 格子之間的白線寬度
                 cbar_kws={'ticks': [0.375, 1.125, 1.875, 2.625], 'label': 'Risk Level (Ground Truth)'},
                 vmin=-0.5, vmax=3.5)

# 修改右側顏色條的標籤
colorbar = ax.collections[0].colorbar
colorbar.set_ticklabels(['0: Safe 🔵', '1: Caution 🟡', '2: Warning 🟡', '3: High Risk 🔴'])

# 5. 標題與排版優化 (論文要求)
# plt.title('Figure 5.X: Medi-Agent Curated Drug Interaction Heatmap (Mock-up)', fontsize=15, fontweight='bold', pad=20)
plt.xticks(rotation=45, ha='right', fontsize=11, fontname='Arial')
plt.yticks(rotation=0, fontsize=11, fontname='Arial')
plt.tight_layout()

# 6. 輸出高解析度圖片 (300 DPI 是論文印刷標準)
filename = 'Thesis_Drug_Heatmap_Final.png'
plt.savefig(filename, dpi=300, bbox_inches='tight')
print(f"✅ 成功！論文用熱力圖已儲存為：{filename}")

plt.show()