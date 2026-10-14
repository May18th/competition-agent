#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成「演示视频_网页版.html」：用真实前端截图做 Ken Burns 运镜 + 真实功能字幕的演示短片。
单文件自包含（截图 base64 内嵌），浏览器打开即播，可一键录屏成 MP4。
注意：本环境无法生成 MP4（VideoGen 被网络墙挡、无 ffmpeg），故用网页版作为可交付的真实画面演示。
"""
import base64, os

REPO = os.path.dirname(os.path.abspath(__file__))
VID = os.path.join(REPO, "artifacts", "demo-video")

def b64(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

hero = b64(os.path.join(VID, "hero_desktop.png"))
desktop = b64(os.path.join(VID, "real_ui_desktop.png"))
mobile = b64(os.path.join(VID, "real_ui_mobile.png"))

scenes = [
    {"img": hero, "kb": "kb-hero", "cap": "科创赛事助手 · AI 驱动的科创竞赛全流程助手",
     "sub": "输入一个创意，自动完成规则解析、同质化检测、申报书 / 路演 PPT / 答辩稿生成"},
    {"img": desktop, "kb": "kb-desk", "cap": "输入创意 → 规则解析 + 同质化检测",
     "sub": "20+ 智能体协同：先读懂赛制与评审标准，再比对历史库规避创意撞车"},
    {"img": mobile, "kb": "kb-mobile", "cap": "移动端适配 · 随时随地生成",
     "sub": "响应式界面，手机端也能完成申报书 / PPT / 答辩稿的一键导出"},
    {"img": hero, "kb": "kb-hero2", "cap": "流式生成 · 评委口径复审 · 一键导出",
     "sub": "Word / PPT / PDF / ZIP 多格式导出，质量闸门保障零绝对化、数据可溯源"},
]

def scene_html(i, s):
    return f'''
    <div class="scene" id="scene{i}">
      <div class="frame"><img class="shot {s['kb']}" src="{s['img']}" alt=""></div>
      <div class="capwrap">
        <div class="cap">{s['cap']}</div>
        <div class="sub">{s['sub']}</div>
      </div>
    </div>'''

scenes_html = "\n".join(scene_html(i, s) for i, s in enumerate(scenes))

narr = [
    "【0:00】大家好，这是「科创赛事助手」——一个用 AI 把科创竞赛从创意到提交全流程跑通的网站。",
    "【0:05】你只需要输入一个创意，系统先做规则解析，读懂赛制、评审标准和往年获奖规律。",
    "【0:12】接着是同质化检测，把你的创意和历史库里上百个作品比对，提前规避撞车和雷同。",
    "【0:20】然后 20 多个智能体协同，流式生成申报书、路演 PPT 和答辩稿，边生成边看。",
    "【0:28】生成后还有评委口径的自动复审，以及质量闸门，保证不写绝对化用语、数据可溯源。",
    "【0:36】最后一键导出 Word、PPT、PDF、ZIP，手机端也能用，随时随地把作品交上去。",
]

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>科创赛事助手 · 产品演示短片</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{height:100%;background:#05070f;overflow:hidden;font-family:"Microsoft YaHei","PingFang SC",sans-serif}}
  #stage{{position:relative;width:100vw;height:100vh;background:#05070f;overflow:hidden}}
  .scene{{position:absolute;inset:0;opacity:0;transition:opacity 1s ease;pointer-events:none}}
  .scene.active{{opacity:1;pointer-events:auto}}
  .frame{{position:absolute;inset:0;overflow:hidden;display:flex;align-items:center;justify-content:center;background:#05070f}}
  .shot{{width:100%;height:100%;object-fit:cover;transform-origin:center}}
  /* Ken Burns 运镜 */
  @keyframes kbHero{{0%{{transform:scale(1.02) translate(0,0)}}100%{{transform:scale(1.12) translate(-1.5%,-1%)}}}}
  @keyframes kbDesk{{0%{{transform:scale(1.05) translateY(0)}}100%{{transform:scale(1.18) translateY(-6%)}}}}
  @keyframes kbMobile{{0%{{transform:scale(1.0) translateX(0)}}100%{{transform:scale(1.12) translateX(3%)}}}}
  .scene.active .kb-hero{{animation:kbHero 6s ease-in-out forwards}}
  .scene.active .kb-desk{{animation:kbDesk 6s ease-in-out forwards}}
  .scene.active .kb-mobile{{animation:kbMobile 6s ease-in-out forwards}}
  .scene.active .kb-hero2{{animation:kbHero 6s ease-in-out forwards}}
  /* 暗角 + 蓝色调，统一科技感 */
  .frame::after{{content:"";position:absolute;inset:0;background:radial-gradient(120% 90% at 50% 40%,transparent 55%,rgba(5,7,15,.75) 100%);pointer-events:none}}
  .capwrap{{position:absolute;left:6%;bottom:9%;max-width:78%;z-index:3;opacity:0;transform:translateY(20px);transition:all .8s ease .5s}}
  .scene.active .capwrap{{opacity:1;transform:translateY(0)}}
  .cap{{font-size:clamp(22px,3.4vw,46px);font-weight:800;color:#fff;letter-spacing:.5px;text-shadow:0 2px 18px rgba(0,0,0,.6)}}
  .cap::before{{content:"";display:inline-block;width:10px;height:34px;background:#818CF8;vertical-align:-4px;margin-right:14px;border-radius:2px}}
  .sub{{margin-top:14px;font-size:clamp(13px,1.5vw,20px);color:#c7d0f0;line-height:1.6;text-shadow:0 2px 12px rgba(0,0,0,.6)}}
  /* 顶部品牌条 */
  .brand{{position:absolute;top:5%;left:6%;z-index:4;display:flex;align-items:center;gap:12px;opacity:0;transition:opacity .8s ease .3s}}
  .scene.active .brand{{opacity:1}}
  .logo{{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#818CF8,#3b5bdb);box-shadow:0 4px 16px rgba(99,102,241,.5)}}
  .bname{{color:#dfe5ff;font-weight:700;font-size:clamp(14px,1.6vw,20px);letter-spacing:1px}}
  /* 进度条 */
  #prog{{position:absolute;left:0;bottom:0;height:4px;width:0;background:linear-gradient(90deg,#818CF8,#F59E0B);z-index:5;transition:width .25s linear}}
  /* 配音稿面板（录制时可隐藏） */
  #narr{{position:absolute;right:18px;top:18px;z-index:6;width:340px;max-height:46vh;overflow:auto;background:rgba(15,21,53,.86);border:1px solid rgba(129,140,248,.4);border-radius:12px;padding:14px 16px;color:#cdd6f4;font-size:13px;line-height:1.7;backdrop-filter:blur(6px)}}
  #narr h4{{color:#818CF8;font-size:13px;margin-bottom:8px;letter-spacing:1px}}
  #narr p{{margin-bottom:7px;color:#aeb8e0}}
  #narr.min{{display:none}}
  #toggle{{position:absolute;right:18px;top:18px;z-index:7;background:#818CF8;color:#0b1020;border:none;border-radius:9px;padding:8px 12px;font-weight:700;cursor:pointer;display:none}}
  #toggle.show{{display:block}}
  #recTip{{position:absolute;left:50%;top:14px;transform:translateX(-50%);z-index:6;color:#8b93b8;font-size:12px;background:rgba(15,21,53,.7);padding:6px 14px;border-radius:20px}}
</style>
</head>
<body>
<div id="stage">
  {scenes_html}
  <div class="brand"><div class="logo"></div><div class="bname">科创赛事助手 KCWX</div></div>
  <div id="recTip">录制提示：点右上「隐藏配音稿」后，用系统录屏捕获本窗口即可得到 MP4 演示视频</div>
  <button id="toggle" onclick="document.getElementById('narr').classList.add('min');this.classList.remove('show');document.getElementById('show').classList.add('show')">显示配音稿</button>
  <div id="narr">
    <h4>配音稿（录制前可读熟，录制时隐藏）</h4>
    {''.join(f'<p>{n}</p>' for n in narr)}
    <button onclick="document.getElementById('narr').classList.add('min');document.getElementById('toggle').classList.add('show')" style="margin-top:8px;background:#818CF8;color:#0b1020;border:none;border-radius:8px;padding:7px 10px;font-weight:700;cursor:pointer">隐藏配音稿</button>
  </div>
  <div id="prog"></div>
</div>
<script>
  const scenes=document.querySelectorAll('.scene');
  const prog=document.getElementById('prog');
  const DUR=6000; let idx=0;
  function show(i){{
    scenes.forEach(s=>s.classList.remove('active'));
    scenes[i].classList.add('active');
    prog.style.width='0%';
    requestAnimationFrame(()=>{{prog.style.transition='width '+DUR+'ms linear';prog.style.width='100%';}});
  }}
  function loop(){{ show(idx); idx=(idx+1)%scenes.length; setTimeout(loop,DUR); }}
  show(0); setTimeout(loop,DUR);
</script>
</body>
</html>'''

out = os.path.join(VID, "演示视频_网页版.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("WROTE", out, "bytes=", len(html))
# 校验 base64 可解码
import re
m = re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)', html)
print("embedded images:", len(m), "decoded ok:", all(len(base64.b64decode(x))>1000 for x in m))
