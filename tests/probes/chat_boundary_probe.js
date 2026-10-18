const assert = require('assert');
const fs = require('fs');

const source = fs.readFileSync(process.argv[2], 'utf8');
assert(source.includes("generation_confirmation"), 'generation confirmation event must be handled');
assert(source.includes("recommendation_candidates"), 'candidate event must be handled');
assert(source.includes("确认生成"), 'generation confirmation needs an explicit action');
assert(source.includes("选择候选 "), 'candidate selection must be explicit');
assert(source.includes("/api/chat_apply_proofread"), 'proofread adoption must use the ownership-checked endpoint');
assert(source.includes("/api/proposal_revision/"), 'proofread card must expose undo through revision endpoint');
assert(source.includes("proactive_suggestions_enabled"), 'proactive suggestions need a persisted preference');
assert(source.includes("关闭主动建议"), 'proactive suggestions need a visible opt-out');
assert(source.includes("修改信息"), 'generation confirmation must offer a non-generating edit path');
assert(source.includes("小可"), 'launcher should identify the assistant by name');
assert(source.includes("st.width = '76px'"), 'launcher should use a compact assistant control, not a speech bubble');
assert(!source.includes("M21 11.5a8.4a8.4"), 'launcher must not use the speech-bubble outline');
console.log('chat boundary probe passed');
