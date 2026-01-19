import sqlite3
import requests
import datetime
from flask import Flask, render_template, request, jsonify
from deep_translator import GoogleTranslator
import webbrowser
from threading import Timer

app = Flask(__name__)
DB_NAME = "vocab.db"

# --- 数据库初始化 ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 创建单词表
    c.execute('''CREATE TABLE IF NOT EXISTS words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT UNIQUE,
                    phonetic TEXT,
                    audio_url TEXT,
                    definitions TEXT,
                    cn_def TEXT,
                    examples TEXT,
                    added_at TIMESTAMP,
                    count INTEGER DEFAULT 1,
                    type TEXT DEFAULT 'word'
                )''')
    conn.commit()
    conn.close()

# --- 辅助函数：获取单词数据 ---
def fetch_word_data(word):
    # 1. 尝试获取英文详细信息 (Free Dictionary API)
    api_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    data = {
        "word": word,
        "phonetic": "",
        "audio": "",
        "definitions": [],
        "examples": [],
        "cn": ""
    }
    
    try:
        # 获取中文释义 (使用 Google Translate 免费库)
        data['cn'] = GoogleTranslator(source='auto', target='zh-CN').translate(word)
        
        # 如果是短语（包含空格），通常API查不到详细信息，直接返回中文翻译
        if " " in word:
            return data

        response = requests.get(api_url)
        if response.status_code == 200:
            res_json = response.json()[0]
            
            # 获取音标
            data['phonetic'] = res_json.get('phonetic', '')
            
            # 获取音频
            for phonetics in res_json.get('phonetics', []):
                if phonetics.get('audio'):
                    data['audio'] = phonetics['audio']
                    break
            
            # 获取释义和例句 (取前3个)
            for meaning in res_json.get('meanings', []):
                part_of_speech = meaning.get('partOfSpeech', '')
                for defense in meaning.get('definitions', [])[:5]:
                    definition_text = f"({part_of_speech}) {defense.get('definition')}"
                    data['definitions'].append(definition_text)
                    if defense.get('example'):
                        data['examples'].append(defense.get('example'))
    except Exception as e:
        print(f"Error fetching data: {e}")
    
    return data

# --- 路由 ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add', methods=['POST'])
def add_word():
    req_data = request.json
    word = req_data.get('word', '').strip()
    entry_type = req_data.get('type', 'word') # 'word' or 'phrase'
    
    if not word:
        return jsonify({"error": "Empty word"}), 400

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 检查单词是否已存在
    c.execute("SELECT count FROM words WHERE word = ?", (word,))
    row = c.fetchone()
    
    if row:
        # 如果存在，次数+1，更新时间
        new_count = row[0] + 1
        c.execute("UPDATE words SET count = ?, added_at = ? WHERE word = ?", 
                  (new_count, datetime.datetime.now(), word))
        conn.commit()
        conn.close()
        return jsonify({"message": "Updated", "word": word})
    else:
        # 如果是新单词，获取数据
        if entry_type == 'phrase':
            # 短语只翻译中文
            cn_def = GoogleTranslator(source='auto', target='zh-CN').translate(word)
            c.execute("INSERT INTO words (word, cn_def, added_at, type) VALUES (?, ?, ?, ?)",
                      (word, cn_def, datetime.datetime.now(), 'phrase'))
        else:
            # 单词获取完整信息
            info = fetch_word_data(word)
            # 将列表转换为字符串存储
            defs_str = "||".join(info['definitions'])
            ex_str = "||".join(info['examples'])
            
            c.execute('''INSERT INTO words 
                         (word, phonetic, audio_url, definitions, cn_def, examples, added_at, count, type) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (info['word'], info['phonetic'], info['audio'], defs_str, info['cn'], ex_str, datetime.datetime.now(), 1, 'word'))
        
        conn.commit()
        conn.close()
        return jsonify({"message": "Added", "word": word})

@app.route('/list', methods=['GET'])
def get_list():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # 让结果像字典一样访问
    c = conn.cursor()
    c.execute("SELECT * FROM words ORDER BY added_at DESC")
    rows = c.fetchall()
    conn.close()
    
    data = []
    for row in rows:
        item = dict(row)
        # 还原分割的字符串
        if item['definitions']: item['definitions'] = item['definitions'].split("||")
        else: item['definitions'] = []
        if item['examples']: item['examples'] = item['examples'].split("||")
        else: item['examples'] = []
        data.append(item)
        
    return jsonify(data)

@app.route('/delete', methods=['POST'])
def delete_word():
    word_id = request.json.get('id')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM words WHERE id = ?", (word_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5001/')

if __name__ == '__main__':
    init_db()
    # 延迟1秒后自动打开浏览器
    # Timer(1, open_browser).start()
    app.run(debug=True, port=5001)