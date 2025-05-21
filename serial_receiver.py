# serial_receiver.py 保持不变，使用原来的代码
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from dataclasses import dataclass

@dataclass
class SerialConfig:
    port: str
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = 'N'
    stopbits: float = 1
    timeout: float = 1

class NMEAParser:
    """NMEA协议解析器"""

    @staticmethod
    def parse_gnrmc(parts):
        """解析GNRMC语句"""
        try:
            # 时间解析
            time_str = parts[1] if len(parts) > 1 and parts[1] else None
            time = f"{time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}" if time_str and len(time_str) >= 6 else "无效时间"

            # 状态检查
            status = parts[2] if len(parts) > 2 else 'V'
            if status != 'A':
                return {
                    'type': 'GNRMC',
                    'time': time,
                    'valid': False,
                    'status': '无效数据'
                }

            # 日期解析
            date_str = parts[9] if len(parts) > 9 and parts[9] else None
            date = f"20{date_str[4:6]}-{date_str[2:4]}-{date_str[0:2]}" if date_str and len(date_str) >= 6 else "无效日期"

            # 经纬度解析
            lat = float(parts[3][:2]) + float(parts[3][2:]) / 60.0 if len(parts) > 3 and parts[3] else 0.0
            if len(parts) > 4 and parts[4] == 'S':
                lat = -lat

            lon = float(parts[5][:3]) + float(parts[5][3:]) / 60.0 if len(parts) > 5 and parts[5] else 0.0
            if len(parts) > 6 and parts[6] == 'W':
                lon = -lon

            speed = float(parts[7]) if len(parts) > 7 and parts[7] else 0.0  # 节
            course = float(parts[8]) if len(parts) > 8 and parts[8] else 0.0  # 度

            return {
                'type': 'GNRMC',
                'time': time,
                'date': date,
                'latitude': lat,
                'longitude': lon,
                'speed': speed * 1.852,  # 转换为km/h
                'course': course,
                'valid': True
            }
        except Exception:
            return {
                'type': 'GNRMC',
                'valid': False,
                'status': '解析错误'
            }

    @staticmethod
    def parse_gngga(parts):
        """解析GNGGA语句"""
        try:
            # 时间解析
            time_str = parts[1] if len(parts) > 1 and parts[1] else None
            time = f"{time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}" if time_str and len(time_str) >= 6 else "无效时间"

            # 定位质量
            quality = int(parts[6]) if len(parts) > 6 and parts[6] else 0
            if quality == 0:
                return {
                    'type': 'GNGGA',
                    'time': time,
                    'valid': False,
                    'status': '无效定位'
                }

            # 经纬度解析
            lat = float(parts[2][:2]) + float(parts[2][2:]) / 60.0 if len(parts) > 2 and parts[2] else 0.0
            if len(parts) > 3 and parts[3] == 'S':
                lat = -lat

            lon = float(parts[4][:3]) + float(parts[4][3:]) / 60.0 if len(parts) > 4 and parts[4] else 0.0
            if len(parts) > 5 and parts[5] == 'W':
                lon = -lon

            satellites = int(parts[7]) if len(parts) > 7 and parts[7] else 0
            hdop = float(parts[8]) if len(parts) > 8 and parts[8] else 0.0
            altitude = float(parts[9]) if len(parts) > 9 and parts[9] else 0.0

            return {
                'type': 'GNGGA',
                'time': time,
                'latitude': lat,
                'longitude': lon,
                'quality': quality,
                'satellites': satellites,
                'hdop': hdop,
                'altitude': altitude,
                'valid': True
            }
        except Exception:
            return {
                'type': 'GNGGA',
                'valid': False,
                'status': '解析错误'
            }

class SerialReceiver(QThread):
    data_received = pyqtSignal(str)  # 数据接收信号
    error_occurred = pyqtSignal(str)  # 错误发生信号

    def __init__(self, config: SerialConfig, port_index: int):
        super().__init__()
        self.config = config
        self.port_index = port_index
        self.serial_port = None
        self._is_connected = False
        self._should_stop = False

    def run(self):
        """接收数据的线程循环"""
        try:
            self.serial_port = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baudrate,
                bytesize=self.config.bytesize,
                parity=self.config.parity,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout
            )
            self._is_connected = True

            # 优化读取参数
            read_chunk_size = 1024  # 每次读取1KB
            max_read_per_loop = 8192  # 每次循环最多读取8KB
            error_count = 0  # 错误计数器
            max_error_count = 5  # 最大允许错误次数

            while not self._should_stop and self.serial_port and self.serial_port.is_open:
                try:
                    # 增加短暂延迟，减少资源占用
                    self.msleep(10)

                    bytes_available = self.serial_port.in_waiting
                    if bytes_available > 0:
                        # 限制单次读取量
                        bytes_to_read = min(bytes_available, max_read_per_loop, read_chunk_size)
                        data = self.serial_port.read(bytes_to_read)

                        # 高效解码
                        try:
                            text_data = data.decode('utf-8', errors='replace')
                        except UnicodeDecodeError:
                            text_data = data.decode('latin1')  # 更宽松的解码方式

                        self.data_received.emit(text_data)
                        error_count = 0  # 重置错误计数器
                    else:
                        # 没有数据时短暂休眠
                        self.msleep(50)

                except serial.SerialException as e:
                    error_count += 1
                    if error_count >= max_error_count:
                        self.error_occurred.emit(f"串口读取错误: {str(e)} (连续错误{error_count}次)")
                        break
                    # 短暂延迟后重试
                    self.msleep(100)

                except OSError as e:
                    # 处理系统资源错误
                    if e.errno == 22:  # 系统资源不足
                        self.error_occurred.emit("系统资源不足，正在尝试恢复...")
                        self.msleep(500)  # 等待系统恢复
                        error_count += 1
                        if error_count >= max_error_count:
                            break
                    else:
                        self.error_occurred.emit(f"系统错误: {str(e)}")
                        break

                except Exception as e:
                    error_count += 1
                    if error_count >= max_error_count:
                        self.error_occurred.emit(f"发生错误: {str(e)}")
                        break
                    self.msleep(100)  # 短暂延迟后重试

        except serial.SerialException as e:
            error_msg = f"串口连接错误: {str(e)}"
            if "PermissionError" in str(e):
                error_msg = "串口已被占用"
            elif "FileNotFoundError" in str(e):
                error_msg = "串口不存在"
            self.error_occurred.emit(error_msg)
        except Exception as e:
            self.error_occurred.emit(f"未知错误: {str(e)}")
        finally:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self._is_connected = False

    def parse_nmea_data(self, data: str):
        """解析NMEA数据，按指定格式输出"""
        lines = data.split('\n')
        output = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('$GNRMC'):
                output.append(f"原始: {line}")
                result = NMEAParser.parse_gnrmc(line.split(','))
                if result['valid']:
                    output.append(
                        f"解析: [GNRMC]\n"
                        f"      时间: {result['time']}\n"
                        f"      日期: {result['date']}\n"
                        f"      位置: {result['latitude']:.6f}°N, {result['longitude']:.6f}°E\n"
                        f"      速度: {result['speed']:.2f} km/h\n"
                        f"      航向: {result['course']:.1f}°\n"
                    )
                else:
                    output.append(f"解析: [GNRMC] {result.get('status', '无效数据')}\n")
                output.append("")

            elif line.startswith('$GNGGA'):
                output.append(f"原始: {line}")
                result = NMEAParser.parse_gngga(line.split(','))
                if result['valid']:
                    output.append(
                        f"解析: [GNGGA]\n"
                        f"      时间: {result['time']}\n"
                        f"      位置: {result['latitude']:.6f}°N, {result['longitude']:.6f}°E\n"
                        f"      质量: {result['quality']}\n"
                        f"      卫星数: {result['satellites']}\n"
                        f"      HDOP: {result['hdop']:.1f}\n"
                        f"      海拔: {result['altitude']:.1f} m\n"
                    )
                else:
                    output.append(f"解析: [GNGGA] {result.get('status', '无效数据')}\n")
                output.append("")

        return '\n'.join(output) if output else None

    def cleanup(self):
        """彻底清理串口资源"""
        self._should_stop = True

        # 断开所有信号连接
        try:
            self.data_received.disconnect()
            self.error_occurred.disconnect()
        except TypeError:
            pass  # 信号未连接时忽略

        # 更安全的线程终止方式
        if self.isRunning():
            self.wait(2000)  # 等待线程结束，最多2秒
            if self.isRunning():
                self.terminate()  # 强制终止线程

        # 确保串口关闭
        if self.serial_port:
            try:
                self.serial_port.close()
            except:
                pass
            finally:
                self.serial_port = None

        # 强制释放资源
        import gc
        gc.collect()

    def disconnect(self):
        """断开串口连接"""
        self._should_stop = True
        if self.isRunning():
            self.wait(1000)  # 等待线程结束，最多1秒
        self._is_connected = False

    @property
    def is_connected(self):
        return self._is_connected

    @staticmethod
    def get_available_ports() -> list:
        """获取所有可用串口"""
        try:
            ports = [port.device for port in serial.tools.list_ports.comports()]
            return sorted(ports)
        except Exception as e:
            print(f"获取串口列表错误: {str(e)}")
            return []

    def get_port_info(self):
        """获取串口详细信息"""
        if not self.serial_port or not self.serial_port.is_open:
            return "串口未连接"

        info = f"""
        端口: {self.serial_port.port}
        波特率: {self.serial_port.baudrate}
        数据位: {self.serial_port.bytesize}
        校验位: {self.serial_port.parity}
        停止位: {self.serial_port.stopbits}
        超时: {self.serial_port.timeout}
        接收缓存: {self.serial_port.in_waiting} 字节
        """
        return info