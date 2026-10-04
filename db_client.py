import sqlite3
from datetime import datetime, timezone

def init_database(db_filename):
    """
    【功能】初始化数据库。如果文件不存在则创建，如果表不存在则建表。
    【输入】
        - db_filename (str): 数据库文件的路径/名称
    【输出】
        - 无
    """
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()

    # 1. 玩家静态字典表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Player_Info (
            UID TEXT PRIMARY KEY,
            Name TEXT NOT NULL,
            Current_Alliance TEXT
        )
    ''')

    # 2. 玩家状态快照表
    # 检查表里有没有 Name 这一列，进行无损升级
    cursor.execute("PRAGMA table_info(Player_Snapshot)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if columns and 'Name' not in columns:
        print("[*] 检测到旧版 Player_Snapshot 表，正在安全升级加入 Name 列...")
        cursor.execute('ALTER TABLE Player_Snapshot RENAME TO Player_Snapshot_old')
        cursor.execute('''
            CREATE TABLE Player_Snapshot (
                Timestamp TEXT NOT NULL,
                UID TEXT NOT NULL,
                Name TEXT,
                Power INTEGER,
                Alliance TEXT,
                Last_Login TEXT,
                PRIMARY KEY (Timestamp, UID)
            )
        ''')
        # 将旧数据插回，Name 用 Player_Info 里的补全，Alliance 尝试映射成 TAG
        cursor.execute('''
            INSERT INTO Player_Snapshot (Timestamp, UID, Name, Power, Alliance, Last_Login)
            SELECT 
                s.Timestamp, 
                s.UID, 
                p.Name, 
                s.Power, 
                COALESCE(a.Tag, s.Alliance), 
                s.Last_Login 
            FROM Player_Snapshot_old s
            LEFT JOIN Player_Info p ON s.UID = p.UID
            LEFT JOIN Alliance_Info a ON p.Current_Alliance = a.AID
        ''')
        cursor.execute('DROP TABLE Player_Snapshot_old')
        print("[+] Player_Snapshot 升级完毕。")
    elif not columns:
        cursor.execute('''
            CREATE TABLE Player_Snapshot (
                Timestamp TEXT NOT NULL,
                UID TEXT NOT NULL,
                Name TEXT,
                Power INTEGER,
                Alliance TEXT,
                Last_Login TEXT,
                PRIMARY KEY (Timestamp, UID)
            )
        ''')

    # 3. 联盟信息表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Alliance_Info (
            AID TEXT PRIMARY KEY,
            Tag TEXT NOT NULL,
            Name TEXT
        )
    ''')

    # 4. 活动目录表 (新加：用来存放预设的活动列表)
    cursor.execute("PRAGMA table_info(Event_Catalog)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if columns and 'Minimum_points' not in columns:
        print("[*] 检测到旧版 Event_Catalog 表，正在安全升级加入 Minimum_points 列...")
        cursor.execute("ALTER TABLE Event_Catalog ADD COLUMN Minimum_points INTEGER DEFAULT 1")
        print("[+] Event_Catalog 升级完毕。")
    elif not columns:
        cursor.execute('''
            CREATE TABLE Event_Catalog (
                Event_ID TEXT PRIMARY KEY,
                Event_Name TEXT NOT NULL,
                Minimum_points INTEGER DEFAULT 1
            )
        ''')
    
    # 初始化预设活动
    # 移除硬编码注入
    # 5. 升级 活动积分大表 (加入 Timestamp)
    # 检查表里有没有 Timestamp 这一列
    cursor.execute("PRAGMA table_info(Event_Score)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if columns and ('Timestamp' not in columns or 'Name' not in columns):
        print("[*] 检测到旧版 Event_Score 表，正在安全升级加入新列...")
        cursor.execute('ALTER TABLE Event_Score RENAME TO Event_Score_old')
        cursor.execute('''
            CREATE TABLE Event_Score (
                Event_ID TEXT NOT NULL,
                Entity_Type TEXT NOT NULL,
                Entity_ID TEXT NOT NULL,
                Name TEXT,
                Timestamp TEXT NOT NULL,
                Score INTEGER,
                Rank INTEGER,
                PRIMARY KEY (Event_ID, Entity_Type, Entity_ID, Timestamp)
            )
        ''')
        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        ts_val = "Timestamp" if 'Timestamp' in columns else f"'{today_utc}'"
        rank_val = "Rank" if 'Rank' in columns else "NULL"
        name_val = "Name" if 'Name' in columns else "NULL"
        
        cursor.execute(f'''
            INSERT INTO Event_Score (Event_ID, Entity_Type, Entity_ID, Name, Timestamp, Score, Rank)
            SELECT Event_ID, Entity_Type, Entity_ID, {name_val}, {ts_val}, Score, {rank_val} FROM Event_Score_old
        ''')
        cursor.execute('DROP TABLE Event_Score_old')
        print("[+] Event_Score 升级完毕。")
    elif not columns:
        # 如果表根本不存在，直接建新表
        cursor.execute('''
            CREATE TABLE Event_Score (
                Event_ID TEXT NOT NULL,
                Entity_Type TEXT NOT NULL,
                Entity_ID TEXT NOT NULL,
                Name TEXT,
                Timestamp TEXT NOT NULL,
                Score INTEGER,
                Rank INTEGER,
                PRIMARY KEY (Event_ID, Entity_Type, Entity_ID, Timestamp)
            )
        ''')

    conn.commit()
    conn.close()
    print(f"[*] 数据库 '{db_filename}' 结构初始化完毕。")

def get_all_events(db_filename):
    """获取所有的预设活动列表"""
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    cursor.execute("SELECT Event_ID, Event_Name FROM Event_Catalog ORDER BY rowid")
    events = cursor.fetchall()
    conn.close()
    return events

def get_all_alliances(db_filename):
    """获取所有的联盟列表"""
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    cursor.execute("SELECT AID, Tag, Name FROM Alliance_Info ORDER BY Tag")
    alliances = cursor.fetchall()
    conn.close()
    return alliances

def get_all_snapshot_dates(db_filename):
    """获取战力快照表中所有的记录日期（倒序）"""
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT Timestamp FROM Player_Snapshot ORDER BY Timestamp DESC")
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def add_event(db_filename, event_id, event_name):
    """添加新的活动到预设活动列表"""
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO Event_Catalog (Event_ID, Event_Name) VALUES (?, ?)
    ''', (event_id, event_name))
    conn.commit()
    conn.close()


def upsert_alliance_roster(db_filename, aid, alliance_info_dict, members_list):
    if not members_list:
        return 0

    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    str_aid = str(aid)
    
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    success_count = 0

    try:
        # ======= 新增动作：更新联盟翻译表 =======
        tag = alliance_info_dict.get("abbr", "Unknown")
        full_name = alliance_info_dict.get("name", "Unknown")
        cursor.execute('''
            INSERT INTO Alliance_Info (AID, Tag, Name)
            VALUES (?, ?, ?)
            ON CONFLICT(AID) DO UPDATE SET
                Tag = excluded.Tag,
                Name = excluded.Name
        ''', (str_aid, tag, full_name))
        for member in members_list:
            # 数据清洗与终极防御性转换
            name = member.get("nick_name")
            if name is None:
                name = "Unknown"
                
            raw_power = member.get("power")
            power = int(raw_power) if raw_power is not None else 0
            
            raw_login = member.get("last_active_at")
            last_login = str(raw_login) if raw_login is not None else ""
            
            raw_uid = member.get("governor_id")
            uid = str(raw_uid) if raw_uid is not None else "0"

            # 动作 1: UPSERT (插入或更新) 玩家花名册 (刚才被你不小心删掉的就在这)
            cursor.execute('''
                INSERT INTO Player_Info (UID, Name, Current_Alliance)
                VALUES (?, ?, ?)
                ON CONFLICT(UID) DO UPDATE SET
                    Name = excluded.Name,
                    Current_Alliance = excluded.Current_Alliance
            ''', (uid, name, str_aid))

            # 动作 2: UPSERT (插入或更新) 今日战力快照
            cursor.execute('''
                INSERT INTO Player_Snapshot (Timestamp, UID, Name, Power, Alliance, Last_Login)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(Timestamp, UID) DO UPDATE SET
                    Name = excluded.Name,
                    Power = excluded.Power,
                    Alliance = excluded.Alliance,
                    Last_Login = excluded.Last_Login
            ''', (today_utc, uid, name, power, tag, last_login))
            
            success_count += 1
            
        conn.commit()
        return success_count
        
    except Exception as e:
        print(f"[-] 数据库批量写入失败: {e}")
        return -1
    finally:
        conn.close()

def upsert_single_player(db_filename, player_dict):
    """
    【功能】将单个玩家的基础数据存入数据库。
    【输入】
        - db_filename (str): 数据库文件名
        - player_dict (dict): 单个玩家的数据字典 (从 API 获取)
    【输出】
        - bool: 成功 True，失败 False
    """
    if not player_dict:
        return False

    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # 提取玩家自身数据
    uid = str(player_dict.get("governor_id"))
    name = player_dict.get("nick_name", "Unknown")
    power = int(player_dict.get("power", 0))
    last_login = str(player_dict.get("last_active_at", ""))
    
    # 尝试提取他的联盟 aid 和 tag
    alliance_node = player_dict.get("alliance") or {}
    aid = str(alliance_node.get("aid", "")) # 如果没有联盟，就是空字符串
    # 尝试拿 TAG，如果没有 TAG 就降级拿缩写 abbr，都没有就填 aid
    tag = str(alliance_node.get("tag", alliance_node.get("abbr", aid)))

    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO Player_Info (UID, Name, Current_Alliance)
            VALUES (?, ?, ?)
            ON CONFLICT(UID) DO UPDATE SET
                Name = excluded.Name,
                Current_Alliance = excluded.Current_Alliance
        ''', (uid, name, aid))

        cursor.execute('''
            INSERT INTO Player_Snapshot (Timestamp, UID, Name, Power, Alliance, Last_Login)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(Timestamp, UID) DO UPDATE SET
                Name = excluded.Name,
                Power = excluded.Power,
                Alliance = excluded.Alliance,
                Last_Login = excluded.Last_Login
        ''', (today_utc, uid, name, power, tag, last_login))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"[-] 单人数据写入失败: {e}")
        return False
    finally:
        conn.close()

def get_entity_mappings(db_filename, entity_type):
    """
    【功能】获取用于匹配的实体 ID 和名称映射字典
    """
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    
    valid_ids = set()
    name_to_id_map = {}
    id_to_name_map = {}
    
    if entity_type == "Player":
        cursor.execute("SELECT Name, UID FROM Player_Info")
        rows = cursor.fetchall()
        name_to_id_map = {row[0].strip(): row[1] for row in rows}
        id_to_name_map = {row[1]: row[0].strip() for row in rows}
        cursor.execute("SELECT UID FROM Player_Info")
        valid_ids = {row[0] for row in cursor.fetchall()}
    elif entity_type == "Alliance":
        cursor.execute("SELECT Tag, AID, Name FROM Alliance_Info")
        for row in cursor.fetchall():
            tag = row[0].strip() if row[0] else ""
            aid = row[1]
            name = row[2].strip() if row[2] else ""
            if tag: name_to_id_map[tag] = aid
            if name: name_to_id_map[name] = aid
            id_to_name_map[aid] = f"[{tag}] {name}" if tag and name else (name or tag)
        cursor.execute("SELECT AID FROM Alliance_Info")
        valid_ids = {row[0] for row in cursor.fetchall()}
        
    conn.close()
    return valid_ids, name_to_id_map, id_to_name_map

def batch_upsert_event_scores(db_filename, matched_data, event_id, entity_type):
    """
    【功能】批量将积分数据插入或更新到数据库中，只负责纯粹的数据库操作
    """
    if not matched_data:
        return True
        
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION;")
        cursor.executemany('''
            INSERT INTO Event_Score (Event_ID, Entity_Type, Entity_ID, Name, Timestamp, Score, Rank)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(Event_ID, Entity_Type, Entity_ID, Timestamp) DO UPDATE SET
                Name = excluded.Name,
                Score = excluded.Score,
                Rank = excluded.Rank
        ''', matched_data)
        conn.commit()
        print(f"[+] 成功将 {len(matched_data)} 条 {entity_type} 积分数据写入数据库 (活动ID: {event_id})。")
        return True
    except Exception as e:
        conn.rollback() 
        print(f"[-] 数据库批量插入处理严重异常，已回滚事务: {e}")
        return False
    finally:
        conn.close()