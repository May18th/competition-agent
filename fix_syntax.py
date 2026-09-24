with open('app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 删掉错误插入的那段
wrong = '''@app.route('/api/generate', methods=['POST'])
def generate():
    tasks = {}


def _run_generation'''
right = '''@app.route('/api/generate', methods=['POST'])
def _run_generation'''
c = c.replace(wrong, right)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(c)
print("修完")
