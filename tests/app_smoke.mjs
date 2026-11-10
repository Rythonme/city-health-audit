/* app.js DOM 桩冒烟测试：加载构建产物数据与前端脚本，验证各视图渲染无异常。
   运行：node tests/app_smoke.mjs  （无外部依赖） */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const load = (p) => readFileSync(join(ROOT, p), 'utf-8');

/* ---- 最小 DOM 桩 ---- */
const elements = new Map();
function stubEl(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id, innerHTML: '', textContent: '', hidden: true, value: '',
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {}, dataset: {}, style: {},
    });
  }
  return elements.get(id);
}
globalThis.document = {
  getElementById: (id) => (id ? stubEl(id) : null),
  querySelectorAll: () => [],
  createElement: () => stubEl('_' + Math.random()),
  body: stubEl('body'),
};
globalThis.window = globalThis;   // app.js 通过 window.CHIA_* 读取，让 window 指向全局
globalThis.scrollTo = () => {};

/* ---- 载入数据与脚本 ---- */
const dataCode = load('docs/data/city_data.js');
const dictCode = load('docs/data/indicator_dictionary.js');
const appCode = load('docs/assets/app.js');

const sandboxData = new Function(dataCode + '\nreturn CHIA_CITY_DATA;')();
const sandboxDict = new Function(dictCode + '\nreturn CHIA_DICT;')();
if (!sandboxData || sandboxData.meta?.data_mode !== 'real') throw new Error('city_data.js 数据无效');
if (!sandboxDict?.indicators?.length) throw new Error('indicator_dictionary.js 数据无效');
globalThis.CHIA_CITY_DATA = sandboxData;
globalThis.CHIA_DICT = sandboxDict;

new Function(appCode)();

/* ---- 断言 ---- */
const $ = (id) => elements.get(id);
const assert = (cond, msg) => { if (!cond) throw new Error('FAIL: ' + msg); };

/* 动态注入的元信息不得是占位符（回归：网站硬编码过期数字） */
for (const id of ['ov-cities', 'ov-period', 'ov-who', 'ov-nmc', 'ft-version']) {
  const v = String($(id)?.textContent ?? '');
  assert(v && !v.includes('—') && v.trim() !== '', `span #${id} 已注入，值=${v}`);
}
assert(!/2003–2018/.test($('ov-period')?.textContent || ''), 'ov-period 不得再是 2003–2018');

/* 四个视图均有内容 */
for (const id of ['overview-kpis', 'overview-dims', 'overview-pm25', 'city-body',
                  'audit-xval', 'audit-stability', 'audit-vardec',
                  'audit-perturb', 'audit-trans', 'audit-region', 'audit-pilot',
                  'dict-body', 'dict-sources']) {
  assert($el(id), id);
}
function $el(id) { const h = $(id)?.innerHTML; return h && h.length > 20; }

/* 新审计组件包含关键数字 */
assert($('audit-perturb').innerHTML.includes('±20%'), 'audit-perturb 渲染扰动情景');
assert($('audit-trans').innerHTML.includes('</svg>'), 'audit-trans 渲染转移矩阵热图');
assert($('audit-region').innerHTML.includes('Hedges'), 'audit-region 渲染已知组效度');

/* 城市情景面板：模拟点击一个城市行 */
const c0 = sandboxData.cities.find((c) => c.scen && c.grade);
if (c0) {
  let rowHandler = null;
  const rowStub = {
    addEventListener(_t, fn) { rowHandler = fn; },
    dataset: { city: c0.name },
    classList: { add() {}, remove() {}, toggle() {} },
  };
  globalThis.document.querySelectorAll = (sel) => (sel === '.city-row' ? [rowStub] : []);
  new Function(appCode)();          // 重新渲染并捕获行点击回调
  if (!rowHandler) throw new Error('FAIL: 城市行点击回调未挂载');
  rowHandler();                     // 触发 selectCity
  assert($('city-detail') && !$('city-detail').hidden, 'city-detail 已展开');
  assert($('city-detail').innerHTML.includes('换方案看档位'), '城市情景面板渲染');
}

console.log('app_smoke: ALL PASS —',
  'meta', sandboxData.meta.version, sandboxData.meta.period,
  '| cities', sandboxData.meta.n_cities,
  '| MC', sandboxData.meta.n_mc);
