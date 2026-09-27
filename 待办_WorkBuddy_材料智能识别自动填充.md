# 待办_WorkBuddy_材料智能识别自动填充

> 来源：Codex（2026-09-28）
> 对象：WorkBuddy（index.html 归你）
> 优先级：P1（减少用户手动输入，是「真实材料进得来」的关键入口）

## 后端接口（已实现，待部署）

`POST /api/parse_material`

请求（二选一）：
- multipart/form-data 上传文件：字段名 `file`，支持 `.pdf / .docx / .txt / .md`（上限 20MB）
- JSON：`{"text": "粘贴的申报书/材料文字"}`

响应：

```json
{
  "success": true,
  "profile": {
    "competition_name": "赛事名称",
    "idea": "项目创意一句话",
    "team": "团队成员信息",
    "user_data": "实测数据与关键指标",
    "keywords": "关键词"
  }
}
```

`profile` 五个字段：材料里有就填、没有就是空字符串（拿不准不编造）。

## 前端要做

1. 输入区顶部加「从材料识别」入口（按钮 / 上传虚线框），支持选 PDF/DOCX/TXT 或直接粘贴文字。
2. 调 `/api/parse_material` 拿到 `profile` 后**自动填充**对应输入框：
   - `competition_name` → 赛事选择
   - `idea` → 创意
   - `team` → 团队成员输入（见上一份「团队信息输入与实测数据强化」交接）
   - `user_data` → 实测数据 / 其它佐证
   - `keywords` → 关键词
3. 自动填充是**建议不是覆盖**：目标框已有内容时弹确认（覆盖 or 跳过）；识别为空的字段标「未识别」。
4. 填充后仍可改，给一句轻提示「识别自材料，请核对」，尤其 team / user_data 识别可能不全。

## 注意

- 别改后端字段名（`profile` 的五个 key 已定）。
- 该接口会消耗一次 LLM 调用（约几秒），前端要有 loading 态。
- 上传文件只用于本次识别，不存共享知识库（隐私保护，同 `/api/upload_pdf` 的 draft 口径）。
