const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const sourcePath = process.argv[2];
const context = {
  window: {},
  document: { readyState: 'loading', addEventListener: function () {} },
  console,
  setTimeout,
  clearTimeout
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), context, { filename: sourcePath });

const chat = context.window.wbChat;
assert(chat, 'chat module should expose its render helpers');

const numericCard = [
  '点评：证据准备充分。',
  '【答辩评分卡】',
  '回应问题：4/5 — 正面回应核心问题。',
  '证据支撑：3分，提供了初步数据。',
  '逻辑表达：5/5 — 结构清楚。',
  '风险意识：2 分，仍需补充预案。',
  '追问：如何验证样本代表性？'
].join('\n');
assert.deepStrictEqual(Array.from(chat.parseDefenseScorecard(numericCard)), [4, 3, 5, 2]);

const squareCard = [
  '答辩评分卡',
  '回应问题：■■■■□',
  '证据支撑：■■■□□',
  '逻辑表达：■■■■■',
  '风险意识：■□□□□'
].join('\n');
assert.deepStrictEqual(Array.from(chat.parseDefenseScorecard(squareCard)), [4, 3, 5, 1]);

const rendered = chat.renderMarkdown(numericCard + '\n\n<img src=x onerror=alert(1)>');
assert(rendered.includes('class="wbchat-scorecard"'), 'valid scorecard should add a visual card');
assert(rendered.includes('<svg viewBox="0 0 240 205" role="img"'), 'visual should be an accessible SVG');
assert(rendered.includes('回应问题 4 分，证据支撑 3 分，逻辑表达 5 分，风险意识 2 分'), 'SVG should expose score labels to assistive technology');
assert(rendered.includes('&lt;img src=x onerror=alert(1)&gt;'), 'untrusted HTML should remain escaped');
assert(!rendered.includes('<img src=x'), 'untrusted HTML must not become an element');

const incomplete = '答辩评分卡\n回应问题：5/5\n证据支撑：4/5\n逻辑表达：3/5';
assert.strictEqual(chat.parseDefenseScorecard(incomplete), null, 'incomplete scorecards should not render');
assert(!chat.renderMarkdown(incomplete).includes('wbchat-scorecard'), 'incomplete scorecards should fall back to Markdown');
assert.strictEqual(chat.parseDefenseScorecard('回应问题：5/5\n证据支撑：4/5\n逻辑表达：3/5\n风险意识：2/5'), null, 'a title is required');
assert.strictEqual(chat.parseDefenseScorecard('答辩评分卡\n回应问题：6/5\n证据支撑：4/5\n逻辑表达：3/5\n风险意识：2/5'), null, 'scores must stay in the 1-5 range');

console.log('chat scorecard probe passed');
