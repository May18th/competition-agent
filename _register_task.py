# -*- coding: utf-8 -*-
"""注册 Windows 计划任务：每 3 分钟跑一次 _guardian.py，服务掉线自动拉起。"""
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

XML = '''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>科创赛事助手 Flask 守护：掉线自动拉起</Description>
    <Author>WorkBuddy</Author>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT3M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-09-25T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>C:\\Users\\34984\\.conda\\envs\\rag-dev\\pythonw.exe</Command>
      <Arguments>_guardian.py</Arguments>
      <WorkingDirectory>C:\\Users\\34984\\Doubao\\chats\\2026-09-23\\new-chat\\科创赛事助手</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''

XML_PATH = r'C:\Users\34984\Doubao\chats\2026-09-23\new-chat\科创赛事助手\_guardian_task.xml'
TASK_NAME = r'科创赛事助手守护'

with open(XML_PATH, 'w', encoding='utf-16') as f:
    f.write(XML)
print('XML 已写入:', XML_PATH)

r = subprocess.run(
    ['schtasks', '/Create', '/TN', TASK_NAME, '/XML', XML_PATH, '/F'],
    capture_output=True, text=True, encoding='utf-8', errors='ignore'
)
print('创建返回码:', r.returncode)
print('stdout:', (r.stdout or '').strip())
print('stderr:', (r.stderr or '').strip())

r2 = subprocess.run(
    ['schtasks', '/Query', '/TN', TASK_NAME, '/V', '/FO', 'LIST'],
    capture_output=True, text=True, encoding='utf-8', errors='ignore'
)
out = (r2.stdout or '')
for key in ['任务名', 'TaskName', '状态', 'Status', '下次运行时间',
            'Next Run Time', '上次结果', 'Last Result', '计划任务',
            'Scheduled Task State', '触发器', 'Triggers']:
    for ln in out.splitlines():
        if ln.startswith(key):
            print(' ', ln.strip())
            break
