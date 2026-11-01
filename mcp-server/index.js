/**
 * Medi-Agent MCP — Drug Interaction MCP Server
 * 碩士論文研究原型（淡江大學 人工智慧機器人碩士班, 2026）
 *
 * ⚠️ 僅供學術研究，不可用於臨床診斷或實際用藥判斷。
 *
 * 資料來源：
 *  - openFDA Drug Label API（美國 FDA 公開資料）
 *  - KingNet 國家網路醫藥（台灣藥品資訊）：僅於使用者提問時即時查詢單筆，
 *    每筆間隔 5 秒，不批量擷取、不儲存或散布網站內容；內容著作權屬原網站所有。
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import express from "express";
import cors from "cors";
import axios from "axios";
import * as cheerio from "cheerio";
import { z } from "zod";
import puppeteer from "puppeteer";

const server = new McpServer({
  name: "Integrated-Medical-Server",
  version: "8.1.0", // V8.1：強化 KingNet 頁面欄位解析
});

// ==========================================
// 🇺🇸 功能模組 1: openFDA 官方仿單交互作用萃取
// ==========================================
async function checkFdaInteraction(drugName) {
  try {
    console.log(`🔍 [FDA API] 正在查詢官方仿單: ${drugName}...`);
    // 使用 openFDA 的 product labeling 端點
    const response = await axios.get(`https://api.fda.gov/drug/label.json?search=openfda.generic_name:"${drugName}"&limit=1`);
    const results = response.data.results;
    
    if (results && results.length > 0 && results[0].drug_interactions) {
      console.log(`✅ [FDA API] 成功獲取 ${drugName} 的交互作用警告！`);
      return results[0].drug_interactions[0];
    }
    
    console.log(`⚠️ [FDA API] 找到 ${drugName} 的仿單，但未特別標註交互作用專區。`);
    return "FDA_NO_SPECIFIC_INTERACTION_SECTION";
    
  } catch (error) { 
    if (error.response && error.response.status === 404) {
       console.log(`❌ [FDA API] 找不到 ${drugName} 的仿單資料。`);
       return "FDA_NOT_FOUND";
    }
    console.error(`❌ [FDA API] 查詢發生錯誤:`, error.message);
    return "FDA_API_ERROR"; 
  }
}

server.tool(
  "check_fda_interactions",
  { drug_names: z.string().describe("【必填參數・強制英文】請將對話中的藥物名稱翻譯為英文學名 (English Generic Name)。例如：'普拿疼'請轉為'Acetaminophen'。多種藥物請以半形逗號分隔。") },
  async ({ drug_names }) => { 
    console.log(`\n🚨 [DEBUG 🇺🇸 FDA] 準備查詢仿單：`, drug_names);
    if (!drug_names) return { content: [{ type: "text", text: "❌ 請提供藥物名稱" }] };
    
    const drugs = drug_names.split(",").map(d => d.trim()).filter(d => d);
    let resultsText = `【🇺🇸 美國 FDA 官方仿單交互作用紀錄】\n`;
    
    for (const drug of drugs) {
        resultsText += `\n▶️ 藥物：[${drug}]\n`;
        const interactionText = await checkFdaInteraction(drug);
        
        if (interactionText === "FDA_NOT_FOUND") {
            resultsText += `  👉 查無此藥物的 FDA 仿單紀錄。\n`;
        } else if (interactionText === "FDA_NO_SPECIFIC_INTERACTION_SECTION") {
            resultsText += `  👉 仿單中未獨立列出交互作用專區。\n`;
        } else if (interactionText === "FDA_API_ERROR") {
            resultsText += `  👉 API 查詢發生異常。\n`;
        } else {
            // FDA 仿單原文極長，截斷保留前 1500 字避免 AI Token 爆量
            resultsText += `  👉 官方原文警告：\n${interactionText.substring(0, 1500)}...\n`;
        }
    }
    
    console.log(`\n========== 🇺🇸 [FDA 查詢成果 LOG] ==========`);
    console.log(resultsText);
    console.log(`============================================\n`);

    return { content: [{ type: "text", text: resultsText }] };
  }
);

// ==========================================
// 🇹🇼 功能模組 2: KingNet 藥物查詢 (擴充交互作用抓取)
// ==========================================
async function scrapeKingNetWithPuppeteer(keyword) {
  let browser = null;
  try {
    console.log(`\n🌐 [Puppeteer] 正在啟動真實瀏覽器模擬查詢: ${keyword}...`);
    browser = await puppeteer.launch({ headless: "new", args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    const page = await browser.newPage();
    
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    await page.setRequestInterception(true);
    page.on('request', (req) => {
        if(req.resourceType() === 'image' || req.resourceType() === 'font'){
            req.abort();
        } else { req.continue(); }
    });

    const encodedKW = encodeURIComponent(keyword);
    const searchUrl = `https://www.kingnet.com.tw/search_google?keyword=${encodedKW}#gsc.tab=0&gsc.q=${encodedKW}&gsc.page=1`;
    
    await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(e => console.log('載入超時，繼續執行'));

    let currentUrl = page.url();
    let isSearchPage = currentUrl.includes('search_google');

    if (isSearchPage) {
            console.log(`👀 [Puppeteer] 正在 Google 搜尋列表頁等待 AJAX 渲染資料...`);
            try {
                // 1. 放寬等待時間，確保 Google 廣告與真實結果都載入
                await page.waitForSelector('.gsc-webResult .gs-title', { timeout: 15000 });
                
                // 2. 關鍵小撇步：強制等待 1.5 秒！讓 Google CSE 把真實的 href 替換上去
                await new Promise(r => setTimeout(r, 1500)); 
                console.log(`🎯 [Puppeteer] 成功捕捉到 Google 搜尋結果！`);
            } catch (e) {
                console.log(`⚠️ [Puppeteer] 經過等待，依然未出現 Google 搜尋結果。`);
            }

            const firstLink = await page.evaluate(() => {
                // 3. 更精準地鎖定搜尋結果內的連結
                const links = Array.from(document.querySelectorAll('.gsc-webResult a.gs-title'));
                for (let a of links) {
                    // Google CSE 有時會把真實網址藏在 data-ctorig 屬性中
                    const url = a.getAttribute('data-ctorig') || a.href;
                    // 放寬判定條件：只要網址有 medicine 或 generic 就當作命中
                    if (url && (url.includes('/medicine/') || url.includes('generic'))) return url;
                }
                return null;
            });

            if (!firstLink) {
                console.log(`⚠️ [Puppeteer] 找不到與「${keyword}」相關的有效商品連結。`);
                await browser.close();
                return null;
            }

            console.log(`🔗 [Puppeteer] 找到真實連結，準備跳轉: ${firstLink}`);
            // 4. 使用 networkidle2 確保內頁完整載入
            await page.goto(firstLink, { waitUntil: 'networkidle2', timeout: 20000 });
            currentUrl = page.url();
        }

    console.log(`📄 [Puppeteer] 抵達商品內頁，開始等待實體資料渲染...`);
    try {
        await page.waitForSelector('h1, h2, h3, .medicine-name, table', { timeout: 10000 });
        console.log(`🎯 [Puppeteer] 內頁資料渲染完畢，開始全網頁掃描！`);
    } catch(e) {}

    // 全頁欄位掃描：依標題關鍵字（成分、適應症、副作用、交互作用）擷取對應內容
    const data = await page.evaluate(() => {
        const getText = (selector) => {
            const el = document.querySelector(selector);
            return el ? el.innerText.trim() : "";
        };

        let chineseName = getText('h1') || getText('h2') || getText('h3') || getText('.medicine-name');
        if (!chineseName) {
            const strongTag = document.querySelector('strong');
            if (strongTag) chineseName = strongTag.innerText.trim();
        }
        if (!chineseName) return null;

        const englishName = getText('h4.medicine-eng-name') || getText('h4') || "";
        
        let ingredient = "";
        let indication = "";
        let sideEffect = "";
        let interaction = "";

        // 掃描頁面中所有文字區塊（不限於 th/td），以因應不同的版面結構
        const allElements = Array.from(document.querySelectorAll('th, td, p, div, li, span'));
        
        for (let i = 0; i < allElements.length; i++) {
            const text = allElements[i].innerText.replace(/\s+/g, '');
            const rawText = allElements[i].innerText.trim();
            
            // 抓取後方內容的輔助函數 (如果是表格就抓下一格，如果是段落就抓文字本身包含的內容)
            const extractContent = (el) => {
                if (el.nextElementSibling && el.nextElementSibling.innerText) {
                    return el.nextElementSibling.innerText.trim();
                } else {
                    // 有時候標題跟內容寫在同一個 div 裡，例如 "成分：阿斯匹靈"
                    return rawText.split(/[:：]/)[1] ? rawText.split(/[:：]/).slice(1).join(':').trim() : "";
                }
            };

            if (!ingredient && (text.includes('主成分') || text.includes('成份') || text === '成分')) {
                ingredient = extractContent(allElements[i]);
            }
            if (!indication && (text.includes('適應症') || text.includes('用途'))) {
                indication = extractContent(allElements[i]);
            }
            if (!sideEffect && (text.includes('副作用') || text.includes('不良反應'))) {
                sideEffect = extractContent(allElements[i]);
            }
            if (!interaction && (text.includes('交互作用') || text.includes('用藥禁忌') || text.includes('禁忌症'))) {
                interaction = extractContent(allElements[i]);
            }
        }

        return { 
            chineseName, 
            englishName, 
            ingredient: ingredient || "成分未特別記載", 
            indication: indication || "詳情請參閱仿單", 
            sideEffect: sideEffect || "未特別記載",
            interaction: interaction || "未特別標註"
        };
    });

    await browser.close(); 
    if (!data) return null;

    let warningLevel = "🔵 注意 (Caution)";
    if (data.sideEffect.includes("休克") || data.sideEffect.includes("出血") || data.sideEffect.includes("禁止") || data.interaction.includes("禁止")) warningLevel = "🔴 危險 (High Risk)";
    else if (data.sideEffect.includes("暈眩") || data.sideEffect.includes("想睡")) warningLevel = "🟡 警告 (Warning)";

    return { ...data, warningLevel, url: currentUrl };
  } catch (error) {
    if (browser) await browser.close();
    return null;
  }
}

server.tool(
  "lookup_taiwan_drug",
  { drug_names: z.string().describe("【必填參數・中英雙軌】請提取對話中的藥物名稱。若使用者輸入大陸譯名或純中文音譯（如：華法林、阿斯匹靈），請務必「附加英文學名」以提高台灣藥典的命中率（格式範例：華法林 Warfarin, 阿斯匹靈 Aspirin）。多種藥物請以半形逗號分隔。若使用者提供的是商品名（如：普拿疼），請同時補上其學名（如：Acetaminophen）進行查詢。") },
  async ({ drug_names }) => { 
    console.log(`\n🚨 [DEBUG 台灣藥庫] 成功收到藥物名稱：`, drug_names);
    if (!drug_names) return { content: [{ type: "text", text: "❌ 請提供藥物名稱" }] };
    
    const drugs = drug_names.split(",").map(d => {
        let name = d.trim().replace(/(請問|感冒藥|止痛藥|胃藥|的成分|成分是什麼|我想問|膠囊|錠劑|膜衣錠|糖漿|顆粒)/g, "");
        if (name.includes("斯斯")) name = "斯斯"; 
        return name.trim();
    }).filter(d => d);

    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
    const results = [];

    for (let i = 0; i < drugs.length; i++) {
        if (i > 0) {
            console.log(`⏳ 查詢間隔 5 秒，降低對來源網站的負擔...`);
            await sleep(5000); 
        }
        const data = await scrapeKingNetWithPuppeteer(drugs[i]);
        results.push({ keyword: drugs[i], data });
    }

    let detailsText = "";
    results.forEach(res => {
       detailsText += `----------------------------------------\n`;
       if (!res.data) {
         detailsText += `❌ 找不到【${res.keyword}】的相關資料。\n`;
       } else {
         detailsText += `💊 藥物: ${res.data.chineseName}\n`;
         if(res.data.englishName) detailsText += `   英文: ${res.data.englishName}\n`;
         detailsText += `🧪 成分: ${res.data.ingredient}\n`;
         detailsText += `⚠️ 警示: ${res.data.warningLevel}\n`;
         detailsText += `⚡ 交互作用: ${res.data.interaction.substring(0, 150)}...\n`; // ✨ 將台灣交互作用也一併印出給 AI
         detailsText += `📋 適應症: ${res.data.indication.substring(0, 80)}...\n🔗 來源: ${res.data.url}\n`;
       }
    });

    console.log(`\n========== 🇹🇼 [KingNet 查詢成果 LOG] ==========\n${detailsText}`);
    return { content: [{ type: "text", text: `🇹🇼 【台灣藥品資料庫批次查詢結果】\n${detailsText}` }] };
  }
);

// ==========================================
// 🚀 啟動 Web Server (SSE)
// ==========================================
const app = express();
app.use(cors());
let transport;
app.get("/sse", async (req, res) => {
  transport = new SSEServerTransport("/messages", res);
  await server.connect(transport);
});
app.post("/messages", async (req, res) => {
  if (transport) await transport.handlePostMessage(req, res);
});
app.listen(3001, () => {
  console.log("✅ Medi-Agent MCP Server (openFDA + KingNet) 運行中: http://localhost:3001/sse");
});