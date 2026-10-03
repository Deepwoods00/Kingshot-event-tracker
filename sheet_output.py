import os
import csv
import sqlite3
from datetime import datetime, timedelta

def export_data_to_csv(prefix, headers, data_rows):
    """
    通用底层导出函数：将数据写入 output/ 目录下的 CSV 文件。
    
    :param prefix: str, 文件名的前缀（例如联盟 Tag，玩家名字，或者 "KVK_Score"）
    :param headers: list, CSV 的表头（例如 ['UID', 'Name', 'Score']）
    :param data_rows: list of tuples/lists, 具体的每行数据
    :return: str, 生成的最终文件路径
    """
    # 1. 确保 output 文件夹存在，如果不存在则自动创建
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # 2. 获取当天日期，格式为 YYYYMMDD
    date_str = datetime.now().strftime("%Y%m%d")
    
    # 3. 动态计算序号，防止覆盖今天已经导出的同名文件
    seq = 1
    while True:
        # 组装文件名，例如: KOR_20260926_1.csv
        filename = f"{prefix}_{date_str}_{seq}.csv"
        filepath = os.path.join(output_dir, filename)
        
        # 如果文件不存在，说明这个序号可用，跳出循环
        if not os.path.exists(filepath):
            break
        seq += 1  # 存在则序号+1，继续检查

    # 4. 执行写入操作
    try:
        # 注意：使用 'utf-8-sig' 编码，可以防止 Excel 打开带中文的 CSV 时出现乱码
        # newline='' 用于防止在 Windows 系统下输出产生多余的空行
        with open(filepath, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            # 先写入表头（支持多行表头）
            if headers:
                if isinstance(headers[0], list):
                    writer.writerows(headers)
                else:
                    writer.writerow(headers)
            # 再批量写入数据行
            if data_rows:
                writer.writerows(data_rows)
                
        print(f"[+] 导出成功！文件已保存至: {filepath}")
        return filepath
        
    except Exception as e:
        print(f"[-] 导出 CSV 失败: {e}")
        return None


def export_latest_player_snapshots(db_file):
    """
    导出最新玩家战力快照表。
    关联了 Player_Info 以获取名字，关联 Alliance_Info 以获取联盟 Tag。
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    print("[*] 正在查询最新战力快照...")
    try:
        # 使用 IFNULL(a.Tag, p.Alliance) 是为了防止联盟信息表里没这个联盟时，显示为空，此时退回显示原始的 AID
        cursor.execute('''
            SELECT p.Timestamp, p.UID, i.Name, p.Power, IFNULL(a.Tag, p.Alliance)
            FROM Player_Snapshot p
            LEFT JOIN Player_Info i ON p.UID = i.UID
            LEFT JOIN Alliance_Info a ON p.Alliance = a.AID
            WHERE p.Timestamp = (
                SELECT MAX(Timestamp) 
                FROM Player_Snapshot 
                WHERE UID = p.UID
            )
            ORDER BY p.Power DESC
        ''')
        rows = cursor.fetchall()
        headers = ["日期", "UID", "玩家昵称", "战力", "联盟"]
        export_data_to_csv("PlayerSnapshot", headers, rows)
    except Exception as e:
        print(f"[-] 数据库查询失败: {e}")
    finally:
        conn.close()


def export_event_scores(db_file, event_id):
    """
    导出特定活动的积分排行
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT Entity_Type, Entity_ID, Name, Timestamp, Score, Rank
            FROM Event_Score
            WHERE Event_ID = ?
            ORDER BY Entity_Type, Score DESC
        ''', (event_id,))
        rows = cursor.fetchall()
        headers = ["实体类型", "ID", "名称", "日期", "分数", "排名"]
        export_data_to_csv(f"Event_{event_id}", headers, rows)
    except Exception as e:
        print(f"[-] 数据库查询失败: {e}")
    finally:
        conn.close()

def export_merged_event_scores(db_file, target_aids, target_events):
    """
    导出活动积分汇总大表（透视表）。
    第一列：联盟 Tag，第二列：玩家名字，后续列：各活动积分（最新日期在最左边）。
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # 1. 获取活动字典和最低分
        cursor.execute("SELECT Event_ID, Event_Name, Minimum_points FROM Event_Catalog")
        event_catalog = {}
        min_scores = {}
        for eid, ename, mscore in cursor.fetchall():
            event_catalog[eid] = ename
            # 处理空缺数据用1代替
            min_scores[eid] = int(mscore) if mscore else 1
        
        # 2. 获取联盟字典 (AID -> Tag)
        cursor.execute("SELECT AID, Tag FROM Alliance_Info")
        aid_to_tag = dict(cursor.fetchall())
        
        # 3. 获取所有玩家信息
        cursor.execute("SELECT UID, Name, Current_Alliance FROM Player_Info")
        player_info = {}
        for uid, name, aid in cursor.fetchall():
            tag = aid_to_tag.get(aid, aid) if aid else "未知"
            player_info[uid] = (name, tag, aid)
            
        # 4. 根据联盟过滤玩家 UID
        valid_uids = set()
        for uid, (name, tag, aid) in player_info.items():
            if target_aids == 'ALL' or str(aid) in target_aids:
                valid_uids.add(uid)
                
        if not valid_uids:
            print("[-] 未找到符合联盟条件的玩家。")
            return
            
        # 5. 查询符合条件的积分数据
        query = "SELECT Entity_ID, Event_ID, Timestamp, Score FROM Event_Score WHERE Entity_Type = 'Player'"
        params = []
        if target_events != 'ALL':
            placeholders = ','.join(['?'] * len(target_events))
            query += f" AND Event_ID IN ({placeholders})"
            params.extend(target_events)
            
        cursor.execute(query, params)
        scores = cursor.fetchall()
        
        # 6. 数据透视处理
        cols_set = set()
        player_scores = {}
        
        for uid, eid, ts, score in scores:
            if uid not in valid_uids:
                continue
            cols_set.add((eid, ts))
            if uid not in player_scores:
                player_scores[uid] = {}
            player_scores[uid][(eid, ts)] = score
            
        if not cols_set:
            print("[-] 该范围内没有找到任何积分数据。")
            return
            
        # 找出近30天的非KVK活动，用于计算平均达标率
        now_time = datetime.now()
        
        recent_non_kvk_cols = []
        for eid, ts in cols_set:
            ename = event_catalog.get(eid, eid)
            if "kvk" not in ename.lower() and "kvk" not in eid.lower():
                try:
                    ts_date = datetime.strptime(ts, "%Y-%m-%d").date()
                    if 0 <= (now_time.date() - ts_date).days <= 30:
                        recent_non_kvk_cols.append((eid, ts))
                except ValueError:
                    pass
                    
        denominator = len(recent_non_kvk_cols)

        # 排序表头：时间倒序（最新在最左边），然后是活动ID
        sorted_cols = sorted(list(cols_set), key=lambda x: x[0])  # 次要排序
        sorted_cols.sort(key=lambda x: x[1], reverse=True)        # 主要排序
        
        # 构造两行表头
        header_row1 = ["", "", "", "non kvk\n(within 30 days)"]
        header_row2 = ["Alliance", "UID", "Name", "Avg(score/min)"]
        for eid, ts in sorted_cols:
            ename = event_catalog.get(eid, eid)
            # 第一行：活动名和日期占用第一格，比值列的表头留空以在Excel中达成合并效果
            header_row1.extend([f"{ename}\n{ts}", ""])
            header_row2.extend(["score", "score/min"])
            
        headers = [header_row1, header_row2]
            
        # 构造行数据
        data_rows = []
        for uid in valid_uids:
            name, tag, aid = player_info.get(uid, ("未知", "未知", "未知"))
            
            # 计算30天平均达标率
            total_ratio = 0.0
            for col in recent_non_kvk_cols:
                eid, ts = col
                score = player_scores.get(uid, {}).get(col, 0)
                min_score = min_scores.get(eid, 1)
                ratio = score / min_score if min_score else 0
                total_ratio += ratio
                
            avg_ratio = round(total_ratio / denominator, 2) if denominator > 0 else 0
            
            row = [tag, uid, name, avg_ratio]
            for col in sorted_cols:
                eid, ts = col
                # 如果没有参加该活动，填 0
                score = player_scores.get(uid, {}).get(col, 0)
                min_score = min_scores.get(eid, 1) # 默认1避免除0错误
                ratio = round(score / min_score, 2) if min_score else 0
                
                row.extend([score, ratio])
            data_rows.append(row)
            
        # 按 联盟 -> 名字 排序
        data_rows.sort(key=lambda x: (x[0], x[2]))
        
        export_data_to_csv("Merged_EventScores", headers, data_rows)
        
    except Exception as e:
        print(f"[-] 导出汇总表时发生错误: {e}")
    finally:
        conn.close()

def export_snapshot_by_date(db_file, target_aids, date_str):
    """
    导出指定日期的战力快照。
    表头: Alliance, UID, Name, Power
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    try:
        query = '''
            SELECT IFNULL(a.Tag, p.Alliance), p.UID, i.Name, p.Power, p.Alliance
            FROM Player_Snapshot p
            LEFT JOIN Player_Info i ON p.UID = i.UID
            LEFT JOIN Alliance_Info a ON p.Alliance = a.AID
            WHERE p.Timestamp = ?
        '''
        cursor.execute(query, (date_str,))
        rows = cursor.fetchall()
        
        data_rows = []
        for tag, uid, name, power, aid in rows:
            if target_aids == 'ALL' or str(aid) in target_aids:
                data_rows.append([tag, uid, name, power])
                
        # 按照 联盟Tag -> 战力降序 排序
        data_rows.sort(key=lambda x: (x[0], -x[3] if isinstance(x[3], int) else 0))
        
        headers = ["Alliance", "UID", "Name", "Power"]
        export_data_to_csv(f"PowerSnapshot_{date_str.replace('-', '')}", headers, data_rows)
    except Exception as e:
        print(f"[-] 导出特定日期快照失败: {e}")
    finally:
        conn.close()