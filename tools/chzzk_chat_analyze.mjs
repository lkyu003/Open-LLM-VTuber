import fs from "node:fs/promises";

const videoNo = process.argv[2] ?? "12408961";
const maxPages = Number(process.argv[3] ?? "500");
const endpoint = (time) =>
  `https://api.chzzk.naver.com/service/v1/videos/${videoNo}/chats?playerMessageTime=${time}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function hhmmss(ms) {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
}

function normalize(content) {
  return String(content ?? "")
    .replace(/\{:(\w+):\}/g, ":$1:")
    .replace(/\s+/g, " ")
    .trim();
}

const chats = [];
let time = 0;
let previousTime = -1;

for (let page = 0; page < maxPages; page += 1) {
  const res = await fetch(endpoint(time), {
    headers: {
      accept: "application/json, text/plain, */*",
      "user-agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      referer: `https://chzzk.naver.com/video/${videoNo}`,
    },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} at playerMessageTime=${time}`);
  }
  const json = await res.json();
  const content = json.content ?? {};
  const pageChats = content.videoChats ?? [];
  for (const chat of pageChats) {
    chats.push({
      t: chat.playerMessageTime,
      time: hhmmss(chat.playerMessageTime),
      content: normalize(chat.content),
      messageTypeCode: chat.messageTypeCode,
    });
  }
  const nextTime = content.nextPlayerMessageTime;
  if (!pageChats.length || nextTime == null || nextTime <= previousTime || nextTime === time) {
    break;
  }
  previousTime = time;
  time = nextTime;
  await sleep(80);
}

const unique = new Map();
for (const chat of chats) {
  const key = `${chat.t}:${chat.content}`;
  if (!unique.has(key)) unique.set(key, chat);
}
const rows = [...unique.values()].sort((a, b) => a.t - b.t);

const freq = new Map();
const tokenFreq = new Map();
const commandFreq = new Map();
const emojiFreq = new Map();
const minuteBuckets = new Map();

for (const row of rows) {
  if (row.content) freq.set(row.content, (freq.get(row.content) ?? 0) + 1);
  const minute = Math.floor(row.t / 60000);
  minuteBuckets.set(minute, (minuteBuckets.get(minute) ?? 0) + 1);
  for (const token of row.content.match(/[ㄱ-ㅎㅏ-ㅣ가-힣A-Za-z0-9_:+/?.!~^-]{2,}/g) ?? []) {
    tokenFreq.set(token, (tokenFreq.get(token) ?? 0) + 1);
  }
  if (/^[/:]{1,2}[A-Za-z가-힣0-9_+:-]+/.test(row.content)) {
    const cmd = row.content.split(/\s+/)[0];
    commandFreq.set(cmd, (commandFreq.get(cmd) ?? 0) + 1);
  }
  for (const emoji of row.content.match(/:\w+:/g) ?? []) {
    emojiFreq.set(emoji, (emojiFreq.get(emoji) ?? 0) + 1);
  }
}

function top(map, n = 40) {
  return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
}

const busiest = top(minuteBuckets, 20).map(([minute, count]) => ({
  time: hhmmss(minute * 60000),
  count,
  samples: rows
    .filter((row) => Math.floor(row.t / 60000) === minute)
    .slice(0, 12)
    .map((row) => row.content),
}));

const samplesByPattern = {
  laughter: rows.filter((r) => /ㅋ{2,}|하하|웃/.test(r.content)).slice(0, 80),
  question: rows.filter((r) => /\?|왜|뭐|어케|어떻게|진짜/.test(r.content)).slice(0, 80),
  greeting: rows.filter((r) => /안녕|하이|방가|어서|왔/.test(r.content)).slice(0, 80),
  game: rows.filter((r) => /다이아|랭크|랭|이터널|루미아|스쿼드|솔랭|캐릭|궁|킬|딜|팀|점수|랭망|겜/.test(r.content)).slice(0, 120),
  reaction: rows.filter((r) => /해명|오|헉|아니|미친|대박|레전드|캬|ㄷㄷ|억까|나이스|좋아|가자|망|죽|살/.test(r.content)).slice(0, 120),
  commands: rows.filter((r) => /^[/:]{1,2}/.test(r.content)).slice(0, 120),
};

const analysis = {
  videoNo,
  totalMessages: rows.length,
  firstTime: rows[0]?.time,
  lastTime: rows.at(-1)?.time,
  topMessages: top(freq, 60),
  topTokens: top(tokenFreq, 80),
  topCommands: top(commandFreq, 50),
  topEmojis: top(emojiFreq, 50),
  busiest,
  samplesByPattern,
};

await fs.writeFile(`chzzk_${videoNo}_chat_analysis.json`, JSON.stringify(analysis, null, 2), "utf8");
await fs.writeFile(
  `chzzk_${videoNo}_chat.tsv`,
  rows.map((r) => `${r.time}\t${r.content}`).join("\n"),
  "utf8",
);

console.log(JSON.stringify({
  videoNo,
  totalMessages: rows.length,
  firstTime: rows[0]?.time,
  lastTime: rows.at(-1)?.time,
  topMessages: top(freq, 20),
  topCommands: top(commandFreq, 20),
  topEmojis: top(emojiFreq, 20),
  busiest: busiest.slice(0, 8),
}, null, 2));
