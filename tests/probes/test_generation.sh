#!/bin/bash
# 计时跑一次 fast 模式生成（异步轮询制）
START=$(date +%s)
RESP=$(curl -s -b tmp_cookies.txt -X POST http://127.0.0.1:8080/api/generate_async \
  -H "Content-Type: application/json" \
  -d '{"competition_name":"iCAN大学生创新创业大赛","idea":"面向大学城学生的智能取件柜：通过柜体格口复用与错峰取件调度，解决快递站高峰期排队取件难的共享取件解决方案","mode":"fast","humanize":"standard","keywords":"","iterate":false,"user_data":"","rule_content":""}')
echo "SUBMIT: $RESP"
TASK=$(echo "$RESP" | python -c "import sys,json;print(json.load(sys.stdin).get('task_id',''))" 2>/dev/null)
if [ -z "$TASK" ]; then echo "NO TASK ID"; exit 1; fi
for i in $(seq 1 120); do
  sleep 3
  S=$(curl -s -b tmp_cookies.txt "http://127.0.0.1:8080/api/status/$TASK")
  ST=$(echo "$S" | python -c "import sys,json;d=json.load(sys.stdin);print(d.get('status',''),d.get('stage',''),d.get('progress',0))" 2>/dev/null)
  echo "[$i] $ST"
  case "$ST" in done*|error*|cancelled*) break;; esac
done
END=$(date +%s)
echo "TOTAL_SECONDS: $((END-START))"
echo "$TASK" > tmp_task_id.txt
