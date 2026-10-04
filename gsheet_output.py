import os
import json
import gspread
from gspread_formatting import *

def export_merged_to_gsheet(headers, data_rows, spreadsheet_id, credentials_file="sheet_api.json", worksheet_name="Data"):
    """
    将汇总数据导出到 Google Sheets，并应用与 Excel 类似的格式。
    
    :param headers: 表头数据
    :param data_rows: 数据行
    :param spreadsheet_id: Google Sheet 的 ID 或 URL
    :param credentials_file: Google API 服务账号 JSON 密钥文件路径
    :param worksheet_name: 写入的工作表名称，如果不存在会自动创建
    """
    if not os.path.exists(credentials_file):
        print(f"[-] 找不到凭据文件 {credentials_file}，无法推送到 Google Sheets。")
        return None

    try:
        print("[*] 正在连接 Google Sheets API...")
        gc = gspread.service_account(filename=credentials_file)
        
        # 尝试打开指定的电子表格
        sh = gc.open_by_key(spreadsheet_id)
        
        # 尝试获取指定名称的工作表，如果不存在则新建
        try:
            worksheet = sh.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=worksheet_name, rows=1000, cols=100)
            print(f"[*] 创建了新的工作表: {worksheet_name}")
            
        print("[*] 正在清空旧数据并写入新数据...")
        worksheet.clear()
        
        # 将 headers 和 data_rows 扁平化为一个2D列表
        all_data = []
        if headers:
            if isinstance(headers[0], list):
                all_data.extend(headers)
            else:
                all_data.append(headers)
        all_data.extend(data_rows)
        
        # 写入所有数据
        worksheet.update('A1', all_data)
        
        print("[*] 正在应用格式样式...")
        
        # 计算行数和列数
        total_rows = len(all_data)
        total_cols = len(all_data[0]) if total_rows > 0 else 0
        
        # 定义样式
        header_fmt = cellFormat(
            horizontalAlignment='CENTER',
            verticalAlignment='MIDDLE',
            wrapStrategy='WRAP'
        )
        data_fmt = cellFormat(
            horizontalAlignment='CENTER',
            verticalAlignment='MIDDLE',
            wrapStrategy='CLIP' # CLIP 或者 OVERFLOW，防止自动换行
        )
        
        # 获取列名例如 'A', 'B', 'Z', 'AA' 等
        def get_col_letter(col):
            letter = ''
            while col > 0:
                col, remainder = divmod(col - 1, 26)
                letter = chr(65 + remainder) + letter
            return letter
            
        max_col_letter = get_col_letter(total_cols)
        
        requests = []
        
        # 1. 设置对齐和换行
        if total_rows >= 2:
            # 前两行表头
            format_cell_range(worksheet, f'A1:{max_col_letter}2', header_fmt)
        if total_rows > 2:
            # 剩余数据行
            format_cell_range(worksheet, f'A3:{max_col_letter}{total_rows}', data_fmt)
            
        # 2. 设置粗边框（右边框加粗）
        thick_right_border = Borders(
            right=Border("SOLID_MEDIUM")
        )
        
        # 收集需要右边框加粗的列（第4列，以及 >=6 的偶数列）
        thick_cols = []
        for c in range(1, total_cols + 1):
            if c == 4 or (c >= 6 and c % 2 == 0):
                thick_cols.append(c)
                
        for c in thick_cols:
            col_letter = get_col_letter(c)
            # 全列加上右边框
            format_cell_range(worksheet, f'{col_letter}1:{col_letter}{total_rows}', cellFormat(borders=thick_right_border))

        # 3. 数字格式
        # 第4列以及所有的 score/min 列 (偶数列 >= 6): '#,##0.00'
        # 所有的 score 列 (奇数列 >= 5): '#,##0'
        float_fmt = cellFormat(numberFormat=NumberFormat(type='NUMBER', pattern='#,##0.00'))
        int_fmt = cellFormat(numberFormat=NumberFormat(type='NUMBER', pattern='#,##0'))
        
        if total_rows > 2:
            for c in range(4, total_cols + 1):
                col_letter = get_col_letter(c)
                if c == 4 or (c >= 6 and c % 2 == 0):
                    format_cell_range(worksheet, f'{col_letter}3:{col_letter}{total_rows}', float_fmt)
                elif c >= 5 and c % 2 != 0:
                    format_cell_range(worksheet, f'{col_letter}3:{col_letter}{total_rows}', int_fmt)

        # 4. 合并第一行的活动名称
        # 假设活动从第5列开始，两两合并
        for c in range(5, total_cols + 1, 2):
            if c + 1 <= total_cols:
                start_col = get_col_letter(c)
                end_col = get_col_letter(c + 1)
                worksheet.merge_cells(f"{start_col}1:{end_col}1")

        # 5. 冻结首2行和左侧4列
        set_frozen(worksheet, rows=2, cols=4)
        
        # 6. 设置数据区域的自动过滤器
        # 我们使用 gspread 原生方法设置 Basic Filter
        # 自动过滤器需要从第二行开始覆盖到所有列和所有数据
        sh.values_update(
            f"{worksheet.title}!A1",
            params={'valueInputOption': 'USER_ENTERED'},
            body={}
        )
        
        # 7. 自动调整列宽 (gspread-formatting 的 autoResize)
        try:
            # 这里的 batchUpdate 尝试调整所有列的宽度
            body = {
                "requests": [
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": worksheet.id,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": total_cols
                            }
                        }
                    },
                    {
                        "setBasicFilter": {
                            "filter": {
                                "range": {
                                    "sheetId": worksheet.id,
                                    "startRowIndex": 1,
                                    "endRowIndex": total_rows,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": total_cols
                                }
                            }
                        }
                    }
                ]
            }
            sh.batch_update(body)
        except Exception as e:
            print(f"[-] 自动调整列宽和过滤器时发生警告: {e}")

        print("[+] 成功推送数据并设置格式到 Google Sheets!")
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={worksheet.id}"
        
    except Exception as e:
        print(f"[-] 导出到 Google Sheets 失败: {e}")
        return None
