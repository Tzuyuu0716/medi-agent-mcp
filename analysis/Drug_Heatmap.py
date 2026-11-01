import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm

# ── 1. 藥物清單 ──────────────────────────────────────────────────
drugs = [
    "Aspirin",
    "Warfarin",
    "Ibuprofen",
    "Acetaminophen\n(Panadol)",
    "Amlodipine",
    "Zolpidem",
    "Tetracycline",
    "Calcium\nCarbonate"
]

# ── 2. Ground Truth 矩陣（三級制）────────────────────────────────
# 0: Caution  (一般安全)
# 1: Warning  (需謹慎)
# 2: High Risk (嚴重交互作用)
# np.nan: 對角線 N/A

data = [
    [np.nan, 2,      1,      0,      0,      0,      0,      0     ],
    [2,      np.nan, 2,      1,      0,      0,      0,      0     ],
    [1,      2,      np.nan, 0,      1,      0,      0,      0     ],
    [0,      1,      0,      np.nan, 0,      0,      0,      0     ],
    [0,      0,      1,      0,      np.nan, 0,      0,      0     ],
    [0,      0,      0,      0,      0,      np.nan, 0,      0     ],
    [0,      0,      0,      0,      0,      0,      np.nan, 2     ],
    [0,      0,      0,      0,      0,      0,      2,      np.nan],
]

df = pd.DataFrame(data, index=drugs, columns=drugs)

# ── 3. 已實驗驗證的組合（用 [V] 取代 ★ 避免字元問題）─────────────
verified = {
    (0, 1), (1, 0),   # Aspirin <-> Warfarin
    (1, 2), (2, 1),   # Warfarin <-> Ibuprofen
    (6, 7), (7, 6),   # Tetracycline <-> Calcium Carbonate
}

# ── 4. 顏色設定 ───────────────────────────────────────────────────
colors = ["#27AE60", "#F39C12", "#E74C3C"]
cmap = ListedColormap(colors)
norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)

# ── 5. 畫布：加大高度，legend 放在圖下方 ─────────────────────────
fig, ax = plt.subplots(figsize=(11, 10))
sns.set_theme(style="white")

mask = df.isnull()
sns.heatmap(
    df,
    ax=ax,
    cmap=cmap,
    norm=norm,
    mask=mask,
    annot=False,
    linewidths=1.2,
    linecolor="white",
    cbar=False,
)

# 對角線填灰
for i in range(len(drugs)):
    ax.add_patch(plt.Rectangle((i, i), 1, 1,
                 fill=True, color="#BDC3C7", zorder=2))
    ax.text(i + 0.5, i + 0.5, "N/A",
            ha="center", va="center",
            fontsize=8, color="#555", zorder=3)

# 格子內標注（純 ASCII，無特殊符號）
risk_label = {0: "0", 1: "1", 2: "2"}
for i in range(len(drugs)):
    for j in range(len(drugs)):
        if i == j:
            continue
        val = df.iloc[i, j]
        if pd.isna(val):
            continue
        v = int(val)
        tag = " [V]" if (i, j) in verified else ""
        ax.text(j + 0.5, i + 0.5, f"{v}{tag}",
                ha="center", va="center",
                fontsize=11, color="white", fontweight="bold", zorder=3)

# ── 6. 軸標籤（純英文，無中文避免亂碼）──────────────────────────
ax.set_xticklabels(drugs, fontsize=10, rotation=35, ha="right")
ax.set_yticklabels(drugs, fontsize=10, rotation=0)
ax.tick_params(axis="both", length=0, pad=6)

# ── 7. 標題 ───────────────────────────────────────────────────────
# ax.set_title(
#     "Medi-Agent MCP  Drug Interaction Risk Heatmap\n"
#     "8 x 8 Ground Truth Matrix  |  Scenario 3 Core Drugs",
#     fontsize=13, fontweight="bold", pad=14, color="#0A2342"
# )

# ── 8. Legend 放在圖下方，不遮住軸標籤 ──────────────────────────
patches = [
    mpatches.Patch(color="#27AE60",
                   label="0  Caution    Generally safe, standard precautions"),
    mpatches.Patch(color="#F39C12",
                   label="1  Warning    Monitor closely, consult physician"),
    mpatches.Patch(color="#E74C3C",
                   label="2  High Risk  Severe interaction, avoid concurrent use"),
    mpatches.Patch(color="#BDC3C7",
                   label="N/A           Same drug (diagonal)"),
]
fig.legend(
    handles=patches,
    loc="lower center",
    bbox_to_anchor=(0.5, 0.01),
    ncol=2,
    fontsize=9,
    framealpha=0.95,
    title="Risk Level Classification  |  [V] = Verified by this study (Scenario 3, n=8)",
    title_fontsize=9,
)

# ── 9. 來源注腳 ───────────────────────────────────────────────────
fig.text(
    0.5, 0.13,
    "Source: openFDA Drug Labeling API  |  Medscape Drug Interaction Checker"
    "  |  KingNet Taiwan Pharmacopoeia\n"
    "For educational reference only - not a substitute for clinical judgment.",
    ha="center", fontsize=8, color="#666", style="italic", linespacing=1.6
)

plt.tight_layout(rect=[0, 0.20, 1, 1])

filename = "Thesis_Drug_Heatmap_Final.png"
plt.savefig(filename, dpi=300, bbox_inches="tight", facecolor="white")
print(f"Saved: {filename}")
plt.show()