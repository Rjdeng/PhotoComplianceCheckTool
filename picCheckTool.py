import requests
import json
import os
import shutil
import time
import pandas as pd
from qiniu import put_file
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from io import BytesIO

# 定义一个空的列表，用于存储每个图片的处理时间数据
timing_data = []

def compress_image(file_path, max_size=256 * 1024, quality=50):
    """
    压缩图片，保持文件大小不超过 max_size（字节）。
    使用 Pillow 库进行压缩。
    """
    # 提前检查文件大小，避免不必要的操作
    file_size = os.path.getsize(file_path)
    
    if file_size <= max_size:
        # 如果文件大小已经小于 max_size，直接返回原路径
        return file_path

    # 打开图片
    img = Image.open(file_path)
    
    # 检查是否是 RGBA 模式，如果是则转换为 RGB 模式
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    
    output = BytesIO()

    # 初始压缩
    img.save(output, format="JPEG", quality=quality)
    output_size = output.tell()

    # 调整质量以继续压缩，直到文件大小小于 max_size
    while output_size > max_size and quality > 10:
        quality -= 5
        output = BytesIO()  # 重置 BytesIO 对象
        img.save(output, format="JPEG", quality=quality)
        output_size = output.tell()

    # 保存压缩后的图片到临时路径
    temp_compressed_path = file_path + ".compressed.jpg"
    with open(temp_compressed_path, "wb") as f:
        f.write(output.getvalue())

    return temp_compressed_path

def get_upload_token(fileName="test.txt"):
    url = "替换自己实际七牛云的接口地址"
    headers = {'Content-Type': 'application/json'}

    data = {
        "appKey": "app-screenshot-review",
        "fileName": fileName
    }

    try:
        # 发送 POST 请求
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()  # 会自动抛出 HTTPError 异常

        # 解析响应
        response_data = response.json()
        data = response_data.get('data', {})
        cached_token  = data.get('token')
        cached_key  = data.get('resourceName')

        if cached_token and cached_key:
            return cached_token, cached_key
        else:
            print("Error: Upload token or key is missing in the response.")
            return "", ""
    except requests.RequestException as e:
        print(f"RequestException: {e}")
        return "", ""
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON response.")
        return "", ""

def upload_file(upload_token, key, filePath):
    try:
        # 上传文件
        ret, info = put_file(up_token=upload_token, key=key, file_path=filePath, version='v2')

        # 检查上传是否成功
        if info.status_code == 200:
            # 获取文件 URL
            file_url = ret.get('data', {}).get('url')
            if file_url:
                # 将 URL 从 HTTPS 转换为 HTTP
                return file_url.replace("https://", "http://")
            else:
                print("Error: 'url' not found in the response data.")
                return ""
        else:
            print(f"Error: Upload failed with status code {info.status_code}.")
            return ""
    except Exception as e:
        print(f"Exception during file upload: {e}")
        return ""

def check_pic_pass(file_url):
    url = "替换自己实际数美云的接口地址"
    # 构造请求参数
    data = {
        "account": "servertest",
        "packageName": "com.eebbk.apps",
        "imageUrl": file_url
    }
    
    try:
        response = requests.post(url,  data=data)
        if response.status_code == 200:
            response_data = response.json()
            print(f"Response data: {response_data}")
            reviewMsg = response_data.get('data', {}).get('reviewMsg')
            return reviewMsg
        else:
            print("Failed to call API. Status code:%s", response.status_code)
        return ""
        
    except Exception as e:
        print("Exception:",e)
        return ""

def process_single_image(file_path, error_folder):
    filename = os.path.basename(file_path)
    
    # 记录开始时间
    start_time = time.time()
    
    # 记录压缩图片的开始时间
    compress_start_time = time.time()
    
    # 压缩大于1MB的图片
    file_path = compress_image(file_path)
    
    # 记录压缩图片的结束时间并打印耗时
    compress_end_time = time.time()
    compress_time = compress_end_time - compress_start_time
    print(f"Step 0 - 压缩图片'{filename}': {compress_time:.2f} 秒")

    # 1、获取上传 Token 和 Key
    token_start_time = time.time()
    token, key = get_upload_token(file_path)
    token_end_time = time.time()
    token_time = token_end_time - token_start_time
    print(f"Step 1 - 获取上传 Token 和 Key'{filename}': {token_time:.2f} 秒")
    
    # 2、上传图片
    upload_start_time = time.time()
    file_url = upload_file(upload_token=token, key=key, filePath=file_path)
    upload_end_time = time.time()
    upload_time = upload_end_time - upload_start_time
    print(f"Step 2 - 上传图片'{filename}': {upload_time:.2f} 秒")
    
    # 3、检查图片
    check_start_time = time.time()
    review_msg = check_pic_pass(file_url)
    check_end_time = time.time()
    check_time = check_end_time - check_start_time
    print(f"Step 3 - 检查图片'{filename}': {check_time:.2f} 秒")
    
    # 4、处理异常图片
    error_check_start_time = time.time()
    if review_msg is not None and '正常' not in review_msg:
        shutil.copy(file_path, os.path.join(error_folder, filename))
    error_check_end_time = time.time()
    error_check_time = error_check_end_time - error_check_start_time
    print(f"Step 4 - 处理异常图片'{filename}': {error_check_time:.2f} 秒")
    
    # 删除临时压缩文件（如果存在）
    if file_path.endswith(".compressed.jpg"):
        os.remove(file_path)
    
    # 计算总时间
    total_time = time.time() - start_time
    print(f"Total time for processing '{filename}': {total_time:.2f} 秒")
    
    # 将每个阶段的时间数据保存到列表中
    timing_data.append({
        '文件名': filename,
        '压缩耗时(秒)': compress_time,
        '获取Token耗时(秒)': token_time,
        '上传耗时(秒)': upload_time,
        '检查耗时(秒)': check_time,
        '处理异常图片耗时(秒)': error_check_time,
        '总耗时(秒)': total_time
    })
    
    # 返回检测结果用于后续的保存
    return {'图片名': filename, '检测结果': review_msg}

# 在所有图片处理完成后，将 timing_data 保存到一个 Excel 文件
def save_timing_data_to_excel(output_excel_name="timing_data.xlsx", image_folder=None):
    if image_folder is None:
        # 如果未指定图片文件夹，使用当前工作目录
        image_folder = os.getcwd()
    
    # 生成保存路径，将 Excel 文件保存到图片文件夹中
    output_excel_path = os.path.join(image_folder, output_excel_name)
    
    # 将 timing_data 保存为 Excel 文件
    df = pd.DataFrame(timing_data)
    df.to_excel(output_excel_path, index=False, engine='openpyxl')
    print(f"Timing data saved to {output_excel_path}")

def process_images_in_folder(input_folder, error_folder, result_file, max_workers=10):
    if not os.path.exists(error_folder):
        os.makedirs(error_folder)

    data = []
    images = [os.path.join(input_folder, filename) for filename in os.listdir(input_folder) 
              if filename.lower().endswith(('.png', '.jpg', '.jpeg'))]

    # 使用 ThreadPoolExecutor 进行并发处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_image, file_path, error_folder) for file_path in images]
        
        # 收集并保存结果
        for future in futures:
            result = future.result()
            data.append(result)

    df = pd.DataFrame(data)
    df.to_excel(result_file, index=False)
    
    save_timing_data_to_excel("timing_data.xlsx", input_folder)

def process_images_in_folder_(input_folder, error_folder, result_file):
    if not os.path.exists(error_folder):
        os.makedirs(error_folder)

    data = []

    # 遍历文件夹中的所有图片
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            file_path = os.path.join(input_folder, filename)
            
            # 1、获取上传 Token 和 Key
            token, key = get_upload_token(file_path)
            
            # 2、上传图片
            file_url = upload_file(upload_token=token, key=key, filePath=file_path)
            
            # 3、检查图片
            review_msg = check_pic_pass(file_url)
            
            # 4、保存检测结果
            data.append({
                '图片名': filename,
                '检测结果': review_msg
            })

            # 如果有异常，将图片拷贝到错误文件夹
            if review_msg is not None and '正常' not in review_msg:
                shutil.copy(file_path, os.path.join(error_folder, filename))

    # 将检测结果保存到 Excel 文件
    df = pd.DataFrame(data)
    df.to_excel(result_file, index=False)

# 检查指定目录下的图片，并将异常图片移动到错误目录，同时生成检测结果的Excel文件
if __name__ == "__main__":
    # 定义输入文件夹路径，其中包含要处理的图片
    input_folder = 'F:\\Work\\PhotoComplianceCheckTool\\resource'
    # 定义错误文件夹路径，异常图片将被移动到这里
    error_folder = 'F:\\Work\\PhotoComplianceCheckTool\\resource\\异常'
    # 定义结果文件路径，将生成一个包含检测结果的Excel文件
    result_file = 'F:\\Work\\PhotoComplianceCheckTool\\resource\\检测结果.xlsx'
    
    # 调用函数，对指定文件夹中的图片进行处理
    process_images_in_folder(input_folder, error_folder, result_file, 8)

   