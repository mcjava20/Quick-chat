import socket
import threading
import os
import time
import logging

# 配置日志记录
logging.basicConfig(filename='chat_file_transfer.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

UPLOAD_FOLDER = "uploads"
DOWNLOAD_FOLDER = "downloads"

# 创建上传和下载文件夹
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# 存储连接的其他节点信息
connected_nodes = {}
# 存储本节点的用户名
username = ""
# 本节点文件传输状态
file_transfer_status = False


def receive_messages(client_socket, node_username):
    global file_transfer_status
    try:
        while True:
            first_byte = client_socket.recv(1)
            if not first_byte:
                logging.info(f"节点 {node_username} 已断开连接。")
                print(f"节点 {node_username} 已断开连接。")
                if client_socket in connected_nodes:
                    del connected_nodes[client_socket]
                break
            if first_byte == b'\x01':
                if file_transfer_status:
                    file_name_length = int.from_bytes(client_socket.recv(4), byteorder='big')
                    file_name = client_socket.recv(file_name_length).decode('utf-8')
                    file_size = int.from_bytes(client_socket.recv(8), byteorder='big')
                    receive_file(client_socket, file_name, file_size)
            else:
                data = first_byte + client_socket.recv(1023)
                message = data.decode('utf-8')
                if message.startswith("BATCH_FILES:"):
                    num_files = int(message.split(":")[1])
                    for _ in range(num_files):
                        file_name_length = int.from_bytes(client_socket.recv(4), byteorder='big')
                        file_name = client_socket.recv(file_name_length).decode('utf-8')
                        file_size = int.from_bytes(client_socket.recv(8), byteorder='big')
                        receive_file(client_socket, file_name, file_size)
                else:
                    print(f"{node_username} 说: {message}")
    except ConnectionResetError:
        logging.warning(f"节点 {node_username} 异常断开连接。")
        print(f"节点 {node_username} 异常断开连接。")
        if client_socket in connected_nodes:
            del connected_nodes[client_socket]
    except Exception as e:
        logging.error(f"接收消息时发生未知错误: {e}")
        print(f"接收消息时发生未知错误: {e}")


def send_messages():
    global file_transfer_status
    try:
        while True:
            message = input(f"{username} 发送: ")
            if message.lower() == "sendall":
                send_all_files()
            elif message.lower().startswith("sendfile:"):
                if file_transfer_status:
                    file_path = message.split(":")[1]
                    if os.path.exists(file_path):
                        send_file_to_all(file_path)
                    else:
                        print("文件不存在。")
                else:
                    print("文件传输未开启，请先输入 :开启文件传输")
            elif message.startswith(":开启文件传输"):
                file_transfer_status = True
                print("文件传输已开启")
            elif message.startswith(":停止文件传输"):
                file_transfer_status = False
                print("文件传输已停止")
            elif message.startswith(":列表"):
                list_online_nodes()
            elif message.startswith(":") and len(message.split()) > 1:
                recipient, content = message[1:].split(" ", 1)
                send_to_specific_node(recipient, content)
            else:
                send_message_to_all(f"{username} 说: {message}")
            if message.lower() == '退出':
                logging.info("你已结束聊天。")
                print("你已结束聊天。")
                for socket in connected_nodes:
                    try:
                        socket.close()
                    except Exception as e:
                        logging.error(f"关闭连接时发生错误: {e}")
                break
    except Exception as e:
        logging.error(f"发送消息时发生未知错误: {e}")
        print(f"发送消息时发生未知错误: {e}")


def receive_file(client_socket, file_name, file_size):
    try:
        file_path = os.path.join(DOWNLOAD_FOLDER, file_name)
        with open(file_path, 'wb') as file:
            received_size = 0
            while received_size < file_size:
                data = client_socket.recv(1024)
                file.write(data)
                received_size += len(data)
        logging.info(f"文件 {file_name} 接收完成。")
        print(f"文件 {file_name} 接收完成。")
    except Exception as e:
        logging.error(f"接收文件时发生错误: {e}")
        print(f"接收文件时发生错误: {e}")


def send_file(client_socket, file_path):
    try:
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        client_socket.send(b'\x01')
        client_socket.send(len(file_name).to_bytes(4, byteorder='big'))
        client_socket.send(file_name.encode('utf-8'))
        client_socket.send(file_size.to_bytes(8, byteorder='big'))
        with open(file_path, 'rb') as file:
            while True:
                data = file.read(1024)
                if not data:
                    break
                client_socket.send(data)
        logging.info(f"文件 {file_name} 发送完成。")
        print(f"文件 {file_name} 发送完成。")
    except Exception as e:
        logging.error(f"发送文件时发生错误: {e}")
        print(f"发送文件时发生错误: {e}")


def send_all_files():
    file_list = os.listdir(UPLOAD_FOLDER)
    num_files = len(file_list)
    for socket in connected_nodes:
        try:
            socket.send(f"BATCH_FILES:{num_files}".encode('utf-8'))
            time.sleep(0.1)
            for file_name in file_list:
                file_path = os.path.join(UPLOAD_FOLDER, file_name)
                send_file(socket, file_path)
        except Exception as e:
            node_username = connected_nodes[socket]
            logging.error(f"向节点 {node_username} 发送批量文件时发生错误: {e}")
            print(f"向节点 {node_username} 发送批量文件时发生错误: {e}")


def send_message_to_all(message):
    for socket in connected_nodes:
        try:
            socket.send(message.encode('utf-8'))
        except Exception as e:
            node_username = connected_nodes[socket]
            logging.error(f"向节点 {node_username} 发送消息失败: {e}")
            print(f"向节点 {node_username} 发送消息失败。")


def send_file_to_all(file_path):
    for socket in connected_nodes:
        send_file(socket, file_path)


def list_online_nodes():
    print("在线节点列表：")
    for socket, node_username in connected_nodes.items():
        address = socket.getpeername()
        print(f"{node_username} - {address}")


def send_to_specific_node(recipient, content):
    for socket, node_username in connected_nodes.items():
        if node_username == recipient:
            try:
                if content.lower().startswith("sendfile:"):
                    if file_transfer_status:
                        file_path = content.split(":")[1]
                        if os.path.exists(file_path):
                            send_file(socket, file_path)
                            socket.send(f"{username} 给你发送了文件 {os.path.basename(file_path)}".encode('utf-8'))
                        else:
                            print("文件不存在。")
                    else:
                        print("文件传输未开启，请先输入 :开启文件传输")
                else:
                    socket.send(f"{username} 对你说: {content}".encode('utf-8'))
            except Exception as e:
                logging.error(f"向 {recipient} 发送消息时发生错误: {e}")
                print(f"向 {recipient} 发送消息时发生错误: {e}")
            return
    print(f"未找到节点 {recipient}")


def start_server():
    server_ip = input("请输入本节点监听的 IP 地址（例如 192.168.1.100），若在本地测试可输入 localhost: ") or 'localhost'
    server_port = int(input("请输入本节点监听的端口号（例如 8888）: "))
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind((server_ip, server_port))
        server.listen(5)
        logging.info(f"本节点正在监听 {server_ip}:{server_port}...")
        print(f"本节点正在监听 {server_ip}:{server_port}...")

        while True:
            client_socket, client_address = server.accept()
            node_username = client_socket.recv(1024).decode('utf-8')
            connected_nodes[client_socket] = node_username
            client_socket.send(username.encode('utf-8'))
            logging.info(f"节点 {node_username} 已连接，地址为 {client_address}")
            print(f"节点 {node_username} 已连接，地址为 {client_address}")
            receive_thread = threading.Thread(target=receive_messages, args=(client_socket, node_username))
            receive_thread.start()
    except OSError as e:
        logging.error(f"服务器启动失败，错误信息: {e}")
        print(f"服务器启动失败，错误信息: {e}")
    finally:
        if 'server' in locals():
            try:
                server.close()
            except Exception as e:
                logging.error(f"关闭服务器时发生错误: {e}")


def connect_to_node():
    target_ip = input("请输入要连接的节点 IP 地址: ")
    target_port = int(input("请输入要连接的节点端口号: "))
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((target_ip, target_port))
        client.send(username.encode('utf-8'))
        node_username = client.recv(1024).decode('utf-8')
        connected_nodes[client] = node_username
        logging.info(f"已连接到节点 {node_username}，地址为 {target_ip}:{target_port}")
        print(f"已连接到节点 {node_username}，地址为 {target_ip}:{target_port}")
        receive_thread = threading.Thread(target=receive_messages, args=(client, node_username))
        receive_thread.start()
    except ConnectionRefusedError:
        logging.warning("无法连接到节点，请检查节点地址和端口是否正确，以及节点是否正在运行。")
        print("无法连接到节点，请检查节点地址和端口是否正确，以及节点是否正在运行。")
    except Exception as e:
        logging.error(f"连接节点时发生未知错误: {e}")
        print(f"连接节点时发生未知错误: {e}")


if __name__ == "__main__":
    username = input("请输入你的用户名: ")
    mode = input("请选择模式（1: 作为服务端等待连接；2: 作为连接端主动连接）: ")

    if mode == '1':
        server_thread = threading.Thread(target=start_server)
        server_thread.start()
    elif mode == '2':
        connect_to_node()
    else:
        print("无效的选择，请输入 1 或 2。")

    send_thread = threading.Thread(target=send_messages)
    send_thread.start()

    if mode == '1':
        server_thread.join()
    send_thread.join()
    