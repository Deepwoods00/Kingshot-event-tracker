import requests

# 模块内部的常量，因为 API 基础地址是永远不变的
BASE_URL = "https://api.mightpulse.com/v1"
# 设置一个统一的超时时间
TIMEOUT = 100 

def fetch_player_info(api_key, governor_id):
    """
    【功能】向服务器请求单个玩家的基础信息。
    【输入】
        - api_key (str): 用于认证的 API 密钥
        - governor_id (str/int): 玩家的唯一 ID
    【输出】
        - 成功: 返回包含玩家信息的字典 (dict)
        - 失败: 返回 None
    """
    url = f"{BASE_URL}/players/{governor_id}?include=base"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code == 200:
            return response.json().get("player", {})
        else:
            print(f"[-] API 报错 (玩家 {governor_id}): HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"[-] 网络请求异常: {e}")
        return None


def fetch_alliance_roster(api_key, kid, tag):
    """
    【功能】向服务器请求某个联盟的完整花名册。
    【输入】
        - api_key (str): 用于认证的 API 密钥
        - kid (str/int): 区服 ID (如 "850")
        - tag (str): 联盟简称 (如 "TOP")
    【输出】
        - 成功: 返回一个元组 (alliance_info字典, members_list列表)
        - 失败: 返回 (None, None)
    """
    url = f"{BASE_URL}/alliances/{kid}/{tag}?include=info,roster"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            alliance_info = data.get("alliance", {})
            members_list = data.get("members", [])
            return alliance_info, members_list
        else:
            print(f"[-] API 报错 (联盟 {tag}): HTTP {response.status_code}")
            return None, None
    except Exception as e:
        print(f"[-] 网络请求异常: {e}")
        return None, None