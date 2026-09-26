import json
import db_client
import tasks

# ================= 基础配置 =================
CONFIG_FILE = "config.json"
# ==========================================

def load_config():
    """读取并解析外部的 JSON 配置文件"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[-] 致命错误：找不到配置文件 {CONFIG_FILE}！请先创建它。")
        return None
    except json.JSONDecodeError:
        print("[-] 致命错误：JSON 格式不正确，请检查逗号和引号！")
        return None

def main():
    """主程序入口：CLI 交互菜单"""
    print("========================================")
    print("      Kingshot 数据监控系统 (v1.0)      ")
    print("      Initialize... Loading Config...   ")
    print("========================================")
    
    # 1. 加载配置文件
    config = load_config()
    if not config:
        return  # 如果配置读取失败，直接退出程序
        
    db_file = config.get("db_file", "kingshot_data.db")
    
    # 2. 启动时先初始化数据库 (如果表没建会自动建)
    db_client.init_database(db_file)

    # 3. 经典的无限循环交互菜单 (PA1 必考题)
    while True:
        print("\n--- 主菜单 ---")
        print("1. [自动] 一键拉取配置表中的所有联盟最新数据 (KVK 打卡用)")
        print("2. [单点] 输入 ID 抓取并更新单个玩家数据")
        print("3. [导出] 导出或分析数据 (开发中...)")
        print("4. [导入] 从 CSV 文件导入活动积分并匹配 UID")
        print("0. 退出系统")
        
        choice = input("\n请输入数字指令 [0-4]: ").strip()
        
        if choice == '1':
            tasks.task_sync_alliances(config)
        elif choice == '2':
            tasks.task_sync_single_player(config)
        elif choice == '3':
            tasks.task_export_data(config)
        elif choice == '4':
            tasks.task_import_csv(config)
        elif choice == '0':
            print("[*] 感谢使用，系统退出。再见！")
            break  # 打破 while 循环，结束程序
        else:
            print("[-] 无效指令，请重新输入。")

if __name__ == "__main__":
    main()