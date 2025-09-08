import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import sqlite3
import re
import os
import sys
import io

# --- 屏蔽 libpng 警告 ---
# 重定向标准错误流以捕获并过滤警告
original_stderr = sys.stderr
sys.stderr = captured_stderr = io.StringIO()

# --- 数据库配置 ---
def resource_path(relative_path):
    """ 获取资源的绝对路径, 兼容开发环境和 PyInstaller 打包环境 """
    try:
        # PyInstaller 创建一个临时文件夹并把路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
# --- 数据库配置 ---
DB_FILE = resource_path("ChineseCommercialCode.db") # 使用新函数定位数据库
TABLE_NAME = "Code"
CHAR_COLUMN = "Ch"
CODE_COLUMN = "ID"

# --- 核心转换逻辑 (无变化) ---
def encode_numbers_to_letters(num_input):
    try:
        num = int(num_input)
        if not (0 <= num <= 9999): return "???"
        if num == 0: return "AAA"
        letters = []
        temp_num = num
        for _ in range(3):
            temp_num, remainder = divmod(temp_num, 26)
            letters.append(chr(ord('A') + remainder))
        return "".join(reversed(letters))
    except (ValueError, TypeError):
        return "???"

def decode_letters_to_numbers(letter_group):
    if not isinstance(letter_group, str) or len(letter_group) != 3 or not letter_group.isalpha(): return "????"
    num = 0
    for char in letter_group.upper():
        num = num * 26 + (ord(char) - ord('A'))
    return f"{num:04d}"

# --- 数据库查询逻辑 (增加日志) ---
class CodeDB:
    def __init__(self, db_file):
        self.db_file = db_file
        if not os.path.exists(self.db_file):
            messagebox.showerror("数据库错误", f"错误：数据库文件 '{self.db_file}' 不存在。")
            sys.exit(1)
        try:
            self.conn = sqlite3.connect(self.db_file)
            print("[LOG] 数据库连接成功。")
        except sqlite3.Error as e:
            messagebox.showerror("数据库错误", f"连接数据库失败: {e}")
            sys.exit(1)

    def char_to_code(self, character):
        try:
            cursor = self.conn.cursor()
            query = f"SELECT {CODE_COLUMN} FROM {TABLE_NAME} WHERE {CHAR_COLUMN} = ?"
            cursor.execute(query, (character,))
            result = cursor.fetchone()
            code = result[0] if result else None
            print(f"[LOG] 查询: 汉字 '{character}' -> 电码 '{code if code is not None else '未找到'}'")
            return code
        except sqlite3.Error as e:
            print(f"[ERROR] 数据库查询错误 (char_to_code): {e}")
            return None

    def code_to_char(self, code):
        try:
            int_code = int(code)
            cursor = self.conn.cursor()
            query = f"SELECT {CHAR_COLUMN} FROM {TABLE_NAME} WHERE {CODE_COLUMN} = ?"
            cursor.execute(query, (int_code,))
            result = cursor.fetchone()
            char = result[0] if result else None
            print(f"[LOG] 查询: 电码 '{code}' -> 汉字 '{char if char else '未找到'}'")
            return char
        except (sqlite3.Error, ValueError) as e:
            print(f"[ERROR] 数据库查询错误 (code_to_char): {e}")
            return None

    def close(self):
        if self.conn:
            self.conn.close()
            print("[LOG] 数据库连接已关闭。")

# --- 图形用户界面 (GUI) ---
class App(tk.Tk):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.title("智能电码转换器")
        self.geometry("750x450")

        # 记录最后修改的文本框
        self.last_modified_widget = None

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.char_text = self.create_entry_box(main_frame, "汉字", 0)
        self.code_text = self.create_entry_box(main_frame, "四位电码", 1)
        self.letter_text = self.create_entry_box(main_frame, "三字母码", 2)
        
        # 绑定事件，记录哪个框最后被修改
        self.char_text.bind("<KeyPress>", lambda e: self.set_last_modified(self.char_text))
        self.code_text.bind("<KeyPress>", lambda e: self.set_last_modified(self.code_text))
        self.letter_text.bind("<KeyPress>", lambda e: self.set_last_modified(self.letter_text))

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(20, 0), sticky="ew")

        # 集成后的转换按钮
        convert_button = ttk.Button(button_frame, text="转换 (Convert)", command=self.smart_convert)
        convert_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        clear_button = ttk.Button(button_frame, text="清空 (Clear)", command=self.clear_all)
        clear_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_entry_box(self, parent, label_text, row):
        label = ttk.Label(parent, text=label_text, font=("Helvetica", 11))
        label.grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=(5, 2))
        text_widget = scrolledtext.ScrolledText(parent, height=5, font=("Consolas", 12), wrap=tk.WORD)
        text_widget.grid(row=row, column=1, sticky="nsew", pady=5)
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        return text_widget

    def set_last_modified(self, widget):
        """记录用户最后操作的输入框"""
        self.last_modified_widget = widget

    def smart_convert(self):
        """智能转换函数，根据最后修改的框来决定转换源"""
        if self.last_modified_widget == self.char_text:
            print("\n[ACTION] 从 '汉字'框 开始转换...")
            self.convert_from_char()
        elif self.last_modified_widget == self.code_text:
            print("\n[ACTION] 从 '电码'框 开始转换...")
            self.convert_from_code()
        elif self.last_modified_widget == self.letter_text:
            print("\n[ACTION] 从 '字母'框 开始转换...")
            self.convert_from_letter()
        else:
            messagebox.showinfo("提示", "请先在任意一个框中输入内容再点击转换。")
            print("\n[WARN] 未检测到任何输入，无法转换。")

    def convert_from_char(self):
        content = self.char_text.get("1.0", tk.END).strip()
        codes_int = []
        for char in content:
            if '\u4e00' <= char <= '\u9fff':
                codes_int.append(self.db.char_to_code(char))
            elif char.strip():
                codes_int.append(None) # 使用None作为占位符
        
        codes_str = [f"{c:04d}" if c is not None else "----" for c in codes_int]
        letters = [encode_numbers_to_letters(c) if c is not None else "----" for c in codes_int]

        self.code_text.delete("1.0", tk.END); self.code_text.insert("1.0", " ".join(codes_str))
        self.letter_text.delete("1.0", tk.END); self.letter_text.insert("1.0", " ".join(letters))
        print("[RESULT] 转换完成。")

    def convert_from_code(self):
        content = self.code_text.get("1.0", tk.END).strip()
        codes = re.findall(r'\d{4}', content)
        chars = [self.db.code_to_char(c) or "?" for c in codes]
        letters = [encode_numbers_to_letters(c) for c in codes]

        self.char_text.delete("1.0", tk.END); self.char_text.insert("1.0", "".join(chars))
        self.letter_text.delete("1.0", tk.END); self.letter_text.insert("1.0", " ".join(letters))
        print("[RESULT] 转换完成。")

    def convert_from_letter(self):
        content = re.sub(r'[^A-Z]', '', self.letter_text.get("1.0", tk.END).upper())
        letter_groups = [content[i:i+3] for i in range(0, len(content), 3)]
        codes = [decode_letters_to_numbers(lg) for lg in letter_groups]
        chars = [self.db.code_to_char(c) or "?" for c in codes]
        
        self.char_text.delete("1.0", tk.END); self.char_text.insert("1.0", "".join(chars))
        self.code_text.delete("1.0", tk.END); self.code_text.insert("1.0", " ".join(codes))
        print("[RESULT] 转换完成。")

    def clear_all(self):
        self.char_text.delete("1.0", tk.END)
        self.code_text.delete("1.0", tk.END)
        self.letter_text.delete("1.0", tk.END)
        self.last_modified_widget = None
        print("\n[ACTION] 所有输入框已清空。")
        
    def on_closing(self):
        self.db.close()
        self.destroy()

# ... (你之前的所有代码保持不变) ...

def restore_stderr_and_print_captured(original_stream, captured_stream):
    """恢复标准错误流并打印被捕获的非libpng警告内容"""
    sys.stderr = original_stream  # 恢复
    captured_content = captured_stream.getvalue()
    if captured_content and "iCCP" not in captured_content:
        print("\n--- Captured Errors/Warnings ---", file=sys.stderr)
        print(captured_content, file=sys.stderr)
        print("--------------------------------", file=sys.stderr)

if __name__ == "__main__":
    # 在主程序块的开头定义 original_stderr，确保它总是存在
    original_stderr = sys.stderr
    captured_stderr = None  # 先声明为 None

    try:
        # 重定向 stderr
        sys.stderr = captured_stderr = io.StringIO()
        
        # 启动程序
        database = CodeDB(DB_FILE)
        app = App(database)
        app.mainloop()

    except Exception as e:
        # 如果启动过程中发生严重错误，恢复 stderr 以便能打印错误信息
        if original_stderr:
            sys.stderr = original_stderr
        messagebox.showerror("严重错误", f"程序启动失败: {e}")
        # 打印到命令行，方便调试打包后的程序
        print(f"[FATAL] 程序启动失败: {e}", file=sys.stderr)

    finally:
        # 确保 captured_stderr 已经被创建后才调用恢复函数
        if original_stderr and captured_stderr:
            restore_stderr_and_print_captured(original_stderr, captured_stderr)

