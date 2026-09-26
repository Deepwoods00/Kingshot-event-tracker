import sqlite3
import os

def init_database():
    # 1. 定义数据库文件名
    db_filename = 'kingshot_data.db'
    
    # 打印提示
    print(f"[*] 正在检查并初始化数据库: {db_filename}")

    # 2. 连接数据库 (如果文件不存在，这句代码会自动创建一个空白的 .db 文件)
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()

    # 3. 执行建表 SQL 语句
    
    # --- 表 1: Player_Info (玩家基础信息表) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Player_Info (
            UID TEXT PRIMARY KEY,
            Name TEXT NOT NULL,
            Current_Alliance TEXT
        )
    ''')
    print("[-] Player_Info 表确认完毕。")

    # --- 表 2: Player_Snapshot (战力快照表) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Player_Snapshot (
            Timestamp TEXT NOT NULL,
            UID TEXT NOT NULL,
            Power INTEGER,
            Alliance TEXT,
            Last_Login TEXT,
            PRIMARY KEY (Timestamp, UID)
        )
    ''')
    print("[-] Player_Snapshot 表确认完毕。")

    # --- 表 3: Event_Score (手动录入活动积分表) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Event_Score (
            Event_ID TEXT NOT NULL,
            Entity_Type TEXT NOT NULL,
            Entity_ID TEXT NOT NULL,
            Score INTEGER,
            Rank INTEGER,
            PRIMARY KEY (Event_ID, Entity_Type, Entity_ID)
        )
    ''')
    print("[-] Event_Score 表确认完毕。")

    # 4. 提交保存并关闭连接
    conn.commit()
    conn.close()
    
    print("[*] 数据库初始化成功！你可以随时在 VS Code 里查看它。")

if __name__ == "__main__":
    init_database()