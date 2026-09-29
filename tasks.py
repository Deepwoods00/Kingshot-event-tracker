import time
import os
import csv
from datetime import datetime, timezone
import api_client
import db_client
import sheet_output

def task_sync_alliances(config):
    """任务：一键同步配置文件里的所有重点联盟"""
    api_key = config.get("api_key")
    targets = config.get("targets", {})
    db_file = config.get("db_file", "kingshot_data.db")
    
    if not api_key:
        print("[-] 配置中未找到 api_key。")
        return

    print("\n[>>>] 开始执行：全服联盟数据轮询拉取 [<<<]")
    
    for kid, tags in targets.items():
        for tag in tags:
            # 1. 调用网络模块拉数据
            info, roster = api_client.fetch_alliance_roster(api_key, kid, tag)
            
            if info and roster:
                # 提取底层 AID
                aid = info.get("aid")
                print(f"    - 解析到 [{tag}] 的真实 AID 为: {aid}")
                
                # 2. 调用数据库模块存数据
                success_count = db_client.upsert_alliance_roster(db_file, aid, info, roster)
                print(f"    - [{tag}] 联盟 {success_count} 名成员数据入库完毕！\n")
            
            # 【核心架构要求】：强制延时 1.5 秒，保护你的 API Key 不被封禁
            time.sleep(1.5)
            
    print("[*] 轮询任务全部完成！")

def task_sync_single_player(config):
    """任务：手动输入 ID，拉取单个玩家"""
    api_key = config.get("api_key")
    db_file = config.get("db_file", "kingshot_data.db")
    governor_id = input("请输入要查询的玩家 ID (governor_id): ").strip()
    
    if not governor_id:
        return
        
    print(f"\n[>>>] 开始获取玩家 {governor_id} 数据 [<<<]")
    player_dict = api_client.fetch_player_info(api_key, governor_id)
    
    if player_dict:
        success = db_client.upsert_single_player(db_file, player_dict)
        if success:
            print(f"[+] 玩家 {player_dict.get('nick_name')} 数据更新成功！\n")


def _process_csv_and_match(csv_filepath, valid_ids, name_to_id_map, id_to_name_map, event_id, entity_type, timestamp):
    """内部辅助函数：读取CSV文件，进行数据清洗并与数据库ID匹配"""
    matched_data = []
    unmatched_names = []
    
    if not os.path.exists(csv_filepath):
        print(f"[-] 错误：找不到文件 '{csv_filepath}'，请检查路径。")
        return None, None

    try:
        with open(csv_filepath, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            if not headers:
                print("[-] 错误：CSV 文件似乎为空或没有表头。")
                return None, None
                
            # 自适应寻找名称列和积分列
            name_key = next((h for h in headers if h.lower() in ['name', '玩家', '昵称', 'player', '联盟', 'tag', 'alliance']), None)
            score_key = next((h for h in headers if h.lower() in ['score', '积分', '分数', 'points']), None)
            id_key = next((h for h in headers if h.lower() in ['id', 'uid', 'aid', '编号', 'gov_id']), None)
            rank_key = next((h for h in headers if h.lower() in ['rank', '排名', '名次', '位次']), None)
            
            if not name_key and not id_key:
                print(f"[-] 错误：无法在 CSV 表头中识别出 '名字' 或 'ID' 列。")
                print(f"    当前表头为: {headers}")
                return None, None
            
            if not score_key:
                print(f"[-] 错误：无法在 CSV 表头中识别出 '积分' 列。")
                print(f"    当前表头为: {headers}")
                return None, None

            for row_num, row in enumerate(reader, start=2):
                raw_name = row.get(name_key) if name_key else None
                raw_id = row.get(id_key) if id_key else None
                raw_score = row.get(score_key)
                raw_rank = row.get(rank_key) if rank_key else None
                
                # 提取并清理数据
                entity_name = str(raw_name).strip() if raw_name else ""
                csv_id = str(raw_id).strip() if raw_id else ""
                
                if not entity_name and not csv_id:
                    continue
                    
                score_str = str(raw_score).strip() if raw_score is not None else '0'
                score_str = score_str.replace(',', '')
                try:
                    score = int(score_str)
                except ValueError:
                    display_name = entity_name or csv_id
                    print(f"[-] 警告：第 {row_num} 行 '{display_name}' 的分数 '{raw_score}' 无法转换为数字，默认为 0。")
                    score = 0
                
                rank = None
                if raw_rank:
                    try:
                        rank = int(str(raw_rank).strip())
                    except ValueError:
                        pass
                
                # --- 核心匹配逻辑：ID 优先，名字兜底 ---
                entity_id = None
                
                # 1. 尝试用 CSV 里的 ID 匹配
                if csv_id:
                    if csv_id in valid_ids:
                        entity_id = csv_id
                    else:
                        print(f"[-] 警告：第 {row_num} 行提供的 ID '{csv_id}' 在数据库中不存在，尝试使用名字匹配。")
                
                # 2. 如果没给 ID 或者 ID 找不到，尝试用名字匹配 (严格区分大小写)
                if not entity_id and entity_name:
                    entity_id = name_to_id_map.get(entity_name)
                
                if entity_id:
                    db_name = id_to_name_map.get(entity_id, entity_name)
                    matched_data.append((event_id, entity_type, entity_id, db_name, timestamp, score, rank))
                else:
                    unmatched_names.append({"name": entity_name, "id": csv_id})
                    
    except csv.Error as e:
        print(f"[-] CSV 解析异常: 格式错误。{e}")
        return None, None
        
    return matched_data, unmatched_names

def _prompt_input_date():
    """辅助函数：让用户输入数据日期，支持留空使用今天"""
    print("\n--- 设置数据日期 ---")
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    date_input = input(f"请输入这批数据所属的日期 (格式 YYYY-MM-DD) [直接回车默认为 {today_utc}]: ").strip()
    
    if not date_input:
        return today_utc
        
    # 简单校验格式
    try:
        datetime.strptime(date_input, '%Y-%m-%d')
        return date_input
    except ValueError:
        print(f"[-] 日期格式错误，已自动使用默认日期: {today_utc}")
        return today_utc

def task_import_csv(config):
    """任务：从 CSV 导入活动数据，遇到缺失 ID 自动调用 API 补全"""
    api_key = config.get("api_key")
    db_file = config.get("db_file", "kingshot_data.db")
    
    print("\n--- 导入设置 ---")
    print("1. 导入 [玩家] 个人积分")
    print("2. 导入 [联盟] 总体积分")
    type_choice = input("请选择导入的主体类型 [1-2]: ").strip()
    
    if type_choice == '1':
        entity_type = "Player"
    elif type_choice == '2':
        entity_type = "Alliance"
    else:
        print("[-] 无效选择，已取消导入。")
        return
        
    csv_path = input("请输入 CSV 文件的完整路径 (例如 data.csv): ").strip()
    if not csv_path:
        print("[-] 路径不能为空。")
        return

    # 活动选项菜单
    events = db_client.get_all_events(db_file)
    print("\n--- 选择活动 ---")
    for idx, (e_id, e_name) in enumerate(events, 1):
        print(f"{idx}. {e_name}")
    
    new_event_idx = len(events) + 1
    print(f"{new_event_idx}. [手动输入新活动]")
        
    event_choice = input(f"请输入活动编号 [1-{new_event_idx}]: ").strip()
    if not event_choice.isdigit() or not (1 <= int(event_choice) <= new_event_idx):
        print("[-] 无效的活动选择。")
        return
        
    choice_idx = int(event_choice)
    if choice_idx == new_event_idx:
        event_name = input("请输入新活动名称: ").strip()
        if not event_name:
            print("[-] 活动名称不能为空。")
            return
        event_id = event_name.replace(" ", "_")
        db_client.add_event(db_file, event_id, event_name)
    else:
        event_id = events[choice_idx - 1][0]
        event_name = events[choice_idx - 1][1]
    
    # 呼出日期输入交互
    target_date = _prompt_input_date()
    
    print(f"\n[>>>] 开始处理 CSV 数据... (活动: {event_name}, 日期: {target_date}) [<<<]")
    
    # 建立重试循环（最多执行2次，防止因 API 拉不到数据陷入无限死循环）
    for attempt in range(2):
        # 1. 向 db_client 请求映射字典
        valid_ids, name_to_id_map, id_to_name_map = db_client.get_entity_mappings(db_file, entity_type)
        
        # 2. 读取并在内存中匹配数据
        matched_data, unmatched = _process_csv_and_match(
            csv_path, valid_ids, name_to_id_map, id_to_name_map, event_id, entity_type, target_date
        )
        
        if unmatched is None and matched_data is None:
            break  # 解析遇到严重错误，直接退出
            
        if matched_data:
            # 3. 将匹配成功的数据通过 db_client 批量入库
            db_client.batch_upsert_event_scores(db_file, matched_data, event_id, entity_type)
            
        if len(unmatched) > 0:
            # 如果是玩家且存在缺失，尝试触发自动补全机制
            if entity_type == "Player":
                print(f"\n[-] 警告：发现 {len(unmatched)} 个玩家在数据库中无记录。")
                missing_ids = [item["id"] for item in unmatched if item["id"]]
                
                if missing_ids:
                    print(f"[*] 触发自动补全机制！开始调用功能2的底层逻辑联网拉取缺失玩家...")
                    success_count = 0
                    for missing_id in missing_ids:
                        print(f"    -> 正在自动获取玩家 ID: {missing_id} ...")
                        player_dict = api_client.fetch_player_info(api_key, missing_id)
                        if player_dict:
                            if db_client.upsert_single_player(db_file, player_dict):
                                success_count += 1
                        time.sleep(1.5)  # API 调用强制延时，防止触发速率限制
                        
                    print(f"[+] 自动补全结束，成功入库 {success_count} 个玩家数据。")
                    
                    if success_count > 0:
                        print("[*] 正在重新执行 CSV 导入匹配...\n")
                        continue  # 进入下一次 for 循环，重新导入积分
                    else:
                        print("[-] 自动补全未能成功抓取到有效数据，停止重试。")
                        break
                else:
                    print("[-] 缺失的记录中没有包含 ID 列（只有名字），无法自动联网抓取。")
                    for item in unmatched:
                        print(f"    - 缺失名字: {item['name']}")
                    break
            else:
                # 联盟数据缺少 Tag 无法单搜，暂不触发自动补全
                print(f"\n[-] 警告：以下 {len(unmatched)} 个联盟在数据库中无记录：")
                for item in unmatched:
                    print(f"    - {item['name'] or 'AID:'+item['id']}")
                break
        else:
            print("\n[+] 完美！所有 CSV 中的名称与 ID 都已成功匹配并入库。")
            break

# ================= I/O 相关 =================

def _prompt_alliance_selection(db_file, config=None):
    """辅助函数：让用户选择联盟范围，返回选中的 AID 列表，或 'ALL'"""
    print("\n--- 联盟范围选择 ---")
    print("1. 核心联盟 (读取自 config.json: core_alliances)")
    print("2. 全部已录入联盟")
    print("3. 手动选择联盟 (输入序号)")
    
    aly_choice = input("请选择联盟范围 [1-3]: ").strip()
    target_aids = []
    
    if aly_choice == '1':
        if config and "core_alliances" in config:
            return config["core_alliances"]
        else:
            print("[-] 配置文件中未定义 core_alliances。")
            return None
    elif aly_choice == '2':
        return 'ALL'
    elif aly_choice == '3':
        alliances = db_client.get_all_alliances(db_file)
        if not alliances:
            print("[-] 数据库中目前没有任何联盟记录。")
            return None
        print("\n--- 已录入联盟 ---")
        for idx, (aid, tag, name) in enumerate(alliances, 1):
            print(f"{idx}. [{tag}] {name}")
        
        idx_str = input("请输入联盟编号 (多个用逗号分隔，如 1,3,4): ").strip()
        try:
            indices = [int(i.strip()) for i in idx_str.split(',') if i.strip()]
            for idx in indices:
                if 1 <= idx <= len(alliances):
                    target_aids.append(alliances[idx-1][0]) # 加入 AID
        except ValueError:
            print("[-] 输入格式错误。")
            return None
        if not target_aids:
            print("[-] 未选择任何有效联盟。")
            return None
        return target_aids
    else:
        print("[-] 无效选择。")
        return None

def _prompt_date_selection(db_file):
    """辅助函数：让用户选择战力快照日期"""
    dates = db_client.get_all_snapshot_dates(db_file)
    if not dates:
        print("[-] 数据库中目前没有任何战力快照记录。")
        return None
        
    print("\n--- 选择战力快照日期 ---")
    for idx, date_str in enumerate(dates, 1):
        print(f"{idx}. {date_str}")
        
    choice = input(f"请输入日期编号 [1-{len(dates)}]: ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(dates)):
        print("[-] 无效的日期选择。")
        return None
        
    return dates[int(choice) - 1]

def task_export_data(config):
    """任务：导出分析数据菜单"""
    db_file = config.get("db_file", "kingshot_data.db")
    
    print("\n--- 数据导出选项 ---")
    print("1. 导出【最新玩家快照】(包含当前战力、联盟等)")
    print("2. 导出【特定活动积分排行】")
    print("3. 导出【活动积分汇总大表】(跨活动透视表)")
    print("4. 导出【特定日期的战力快照】")
    print("0. 返回主菜单")
    
    sub_choice = input("请选择导出内容 [0-4]: ").strip()
    
    if sub_choice == '1':
        sheet_output.export_latest_player_snapshots(db_file)
    elif sub_choice == '2':
        events = db_client.get_all_events(db_file)
        if not events:
            print("[-] 数据库中目前没有任何活动。")
            return
            
        print("\n--- 选择要导出的活动 ---")
        for idx, (e_id, e_name) in enumerate(events, 1):
            print(f"{idx}. {e_name}")
            
        event_choice = input(f"请输入活动编号 [1-{len(events)}]: ").strip()
        if not event_choice.isdigit() or not (1 <= int(event_choice) <= len(events)):
            print("[-] 无效的活动选择。")
            return
            
        event_id = events[int(event_choice) - 1][0]
        sheet_output.export_event_scores(db_file, event_id)
        
    elif sub_choice == '3':
        target_aids = _prompt_alliance_selection(db_file, config)
        if not target_aids:
            return
            
        # --- 活动范围选择 ---
        print("\n--- 活动范围选择 ---")
        print("1. 全部历史活动数据")
        print("2. 手动选择活动 (输入序号)")
        
        evt_choice = input("请选择活动范围 [1-2]: ").strip()
        target_events = []
        
        if evt_choice == '1':
            target_events = 'ALL'
        elif evt_choice == '2':
            events = db_client.get_all_events(db_file)
            if not events:
                print("[-] 数据库中目前没有任何活动。")
                return
            print("\n--- 已录入活动 ---")
            for idx, (e_id, e_name) in enumerate(events, 1):
                print(f"{idx}. {e_name}")
            
            idx_str = input("请输入活动编号 (多个用逗号分隔，如 1,2): ").strip()
            try:
                indices = [int(i.strip()) for i in idx_str.split(',') if i.strip()]
                for idx in indices:
                    if 1 <= idx <= len(events):
                        target_events.append(events[idx-1][0]) # 加入 Event_ID
            except ValueError:
                print("[-] 输入格式错误。")
                return
            if not target_events:
                print("[-] 未选择任何有效活动。")
                return
        else:
            print("[-] 无效选择。")
            return
            
        sheet_output.export_merged_event_scores(db_file, target_aids, target_events)
        
    elif sub_choice == '4':
        target_aids = _prompt_alliance_selection(db_file, config)
        if not target_aids:
            return
            
        date_str = _prompt_date_selection(db_file)
        if not date_str:
            return
            
        sheet_output.export_snapshot_by_date(db_file, target_aids, date_str)
    
    elif sub_choice == '0':
        return
    else:
        print("[-] 无效指令。")
