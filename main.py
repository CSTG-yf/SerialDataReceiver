from doctest import FAIL_FAST
import serial,qdarkstyle
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QGroupBox, QScrollArea, QFileDialog,
                             QMessageBox, QGridLayout, QSizePolicy, QCheckBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QFrame, QTextEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont
from serial_receiver import SerialReceiver, SerialConfig
import sys
import os
from datetime import datetime
import pyqtgraph as pg  # 新增绘图库导入
from PyQt5.QtGui import QIcon  # 新增图标类导入


class SerialPortWidget(QWidget):
    """单个串口控件，带标题的紧凑布局"""
    # 新增：连接状态变化信号定义
    connection_state_changed = pyqtSignal()

    def __init__(self, port_index: int, parent=None):
        super().__init__(parent)
        self.port_index = port_index
        self.serial_receiver = None
        self.is_receiving = True
        self.max_display_length = 200000
        self.max_buffer_length = 500000
        self.data_buffer = ""
        self.parsed_data_buffer = ""

        # 文件保存相关
        self.log_dir = "serial_logs"
        self.current_log_file = None
        self.max_file_size = 500 * 1024 * 1024  # 500MB
        self.auto_save_enabled = True  # 默认开启自动保存
        self.bytes_written = 0
        self.file_write_buffer = ""
        self.file_write_threshold = 8192  # 8KB

        # 初始化 data_values 属性（替换QTextEdit为QLabel）
        self.data_values = {
            'time': QLabel("-"),
            'lat': QLabel("-"),
            'lon': QLabel("-"),
            'speed': QLabel("-"),
            'course': QLabel("-"),
            'satellites': QLabel("-"),
            'altitude': QLabel("-")
        }

        # 新增：定义各数据项的工具提示文本
        data_tooltips = {
            'time': '时间',
            'lat': '纬度（°）',
            'lon': '经度（°）',
            'speed': '速度（节）',
            'course': '航向（°）',
            'satellites': '可用卫星数量',
            'altitude': '海拔（米）'
        }

        # 修改循环为遍历键值对（原遍历values()）
        for key, value in self.data_values.items():
            value.setAlignment(Qt.AlignCenter)  # 居中对齐
            value.setStyleSheet("""
                QLabel {
                    padding: 2px;
                    border: 1px solid #eee;
                    border-radius: 3px;
                    background: #f8f8f8;
                }
            """)
            # 新增：设置工具提示
            value.setToolTip(data_tooltips[key])

        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)

        # 初始化绘图数据存储（时间戳和各参数值）
        self.plot_data = {
            'time': [],  # 存储时间戳（秒数）
            'lat': [],
            'lon': [],
            'speed': [],
            'course': [],
            'satellites': [],
            'altitude': []
        }
        self.max_plot_points = 1000  # 最多保存1000个点

        # 关键修复：初始化 last_display_data
        self.last_display_data = {}  # 新增

        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setHorizontalSpacing(5)

        # 串口标识（原50→40）
        self.port_label = QLabel(f"串口{self.port_index}")
        self.port_label.setFixedWidth(50)
        self.port_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.port_label, 0, 0)

        # 串口选择（原120→100）
        self.port_combo = QComboBox()
        self.port_combo.setFixedWidth(100)
        self.refresh_ports()
        # 新增：绑定选择变化事件并初始化工具提示
        self.port_combo.currentTextChanged.connect(self.update_port_tooltip)
        self.update_port_tooltip()  # 初始设置工具提示
        layout.addWidget(self.port_combo, 0, 1)

        # 波特率选择（原80→70）
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(['9600', '14400','19200', '28800','38400', '57600', '115200','230400','460800','921600'])
        self.baudrate_combo.setCurrentText('115200')
        self.baudrate_combo.setFixedWidth(80)
        layout.addWidget(self.baudrate_combo, 0, 2)

        # 连接按钮（原60→50）
        self.connect_btn = QPushButton("连接")
        self.connect_btn.setFixedWidth(50)
        self.connect_btn.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_btn, 0, 3)

        # 自动保存开关
        self.auto_save_check = QCheckBox("自动保存")
        self.auto_save_check.setChecked(True)  # 默认选中自动保存
        self.auto_save_check.stateChanged.connect(self.toggle_auto_save)
        layout.addWidget(self.auto_save_check, 0, 4)

        # 新增：显示当前保存的文件名
        self.filename_label = QLabel("未保存")
        self.filename_label.setAlignment(Qt.AlignLeft)
        self.filename_label.setTextInteractionFlags(Qt.TextSelectableByMouse)  # 新增可选中属性
        self.filename_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # 允许水平扩展
        self.filename_label.setWordWrap(True)  # 允许自动换行
        layout.addWidget(self.filename_label, 0, 5, 1, 1)  # 添加伸缩因子，让标签能扩展

        # 数据量显示
        self.data_size_label = QLabel("0KB")
        self.data_size_label.setFixedWidth(70)
        self.data_size_label.setToolTip("已记录：0 KB（0 字节）")  # 初始提示
        layout.addWidget(self.data_size_label, 0, 6)  # 原列7→列6

        # 数据值显示区域（从列7开始）
        data_labels = ["time", "lat", "lon", "speed", "course", "satellites", "altitude"]
        for col, key in enumerate(data_labels, start=7):
            value = self.data_values[key]
            value.setMinimumWidth(80)  # 替换固定宽度为最小宽度
            value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # 允许水平扩展
            value.setAlignment(Qt.AlignCenter)
            font = QFont()
            font.setPointSize(10)
            value.setFont(font)
            value.setStyleSheet("""
                QLabel {
                    padding: 2px;
                    border: 1px solid #eee;
                    border-radius: 3px;
                    background: #f8f8f8;
                    color: black; 
                }
            """)
            layout.addWidget(value, 0, col)
            layout.setColumnStretch(col, 1)

        # 详情按钮（原60→50）
        self.details_btn = QPushButton("详情")
        self.details_btn.setFixedWidth(50)
        self.details_btn.setEnabled(False)
        self.details_btn.clicked.connect(self.show_port_details)
        layout.addWidget(self.details_btn, 0, 14)

        self.setLayout(layout)

        # 设置定时器更新UI
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(100)  # 100ms更新一次

    def refresh_ports(self):
        """刷新可用串口列表（显示COM3，工具提示显示完整描述）"""
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = SerialReceiver.get_available_ports()  # 现在获取(设备名, 描述)列表
        
        for device, description in ports:
            self.port_combo.addItem(device)  # 下拉列表显示设备名（如COM3）
            # 为每个选项设置工具提示为完整描述
            self.port_combo.setItemData(self.port_combo.count()-1, description, Qt.ToolTipRole)
        
        if current_port in [device for device, _ in ports]:
            self.port_combo.setCurrentText(current_port)
        self.update_port_tooltip()  # 初始设置工具提示

    def update_display(self):
        """更新数据显示（增加强制更新逻辑）"""
        if not self.parsed_data_buffer:
            return

        # 解析最新数据
        lines = self.parsed_data_buffer.split('\n')
        latest_gga = {}
        latest_rmc = {}

        for line in lines:
            if "解析: [GNGGA]" in line and "无效" not in line:
                latest_gga = {}
            elif "解析: [GNRMC]" in line and "无效" not in line:
                latest_rmc = {}
            elif "时间:" in line:
                # 修复：合并split后的剩余部分获取完整时间
                time = ":".join(line.split(":")[1:]).strip()  # 原错误行修改
                if latest_gga:
                    latest_gga["time"] = time
                elif latest_rmc:
                    latest_rmc["time"] = time
            elif "位置:" in line:
                pos_parts = line.split(":")[1].strip().split(", ")
                lat = pos_parts[0].split("°")[0]
                lon = pos_parts[1].split("°")[0]
                if latest_gga:
                    latest_gga["lat"] = lat
                    latest_gga["lon"] = lon
                elif latest_rmc:
                    latest_rmc["lat"] = lat
                    latest_rmc["lon"] = lon
            elif "卫星数:" in line:
                latest_gga["satellites"] = line.split(":")[1].strip()
            elif "海拔:" in line:
                latest_gga["altitude"] = line.split(":")[1].strip().split(" ")[0]
            elif "速度:" in line:
                latest_rmc["speed"] = line.split(":")[1].strip().split(" ")[0]
            elif "航向:" in line:
                latest_rmc["course"] = line.split(":")[1].strip().split("°")[0]

        # 计算新的显示数据
        new_display_data = {
            'time': latest_rmc.get("time", latest_gga.get("time", "-")),
            'lat': latest_rmc.get("lat", latest_gga.get("lat", "-")),
            'lon': latest_rmc.get("lon", latest_gga.get("lon", "-")),
            'speed': latest_rmc.get("speed", "-"),
            'course': latest_rmc.get("course", "-"),
            'satellites': latest_gga.get("satellites", "-"),
            'altitude': latest_gga.get("altitude", "-")
        }

        # 记录上一次显示的数据（新增时间戳）
        if not hasattr(self, 'last_update_time'):
            self.last_update_time = datetime.now().timestamp()

        current_time = datetime.now().timestamp()
        # 关键修改：即使数据未变化，每5秒强制更新
        force_update = (current_time - self.last_update_time) > 5

        if new_display_data != self.last_display_data or force_update:
            # 记录当前时间戳（秒数）
            current_time = datetime.now().timestamp()
            self.plot_data['time'].append(current_time)

            # 尝试转换并添加参数值（处理无效数据时填充NaN）
            try:
                self.plot_data['lat'].append(float(new_display_data['lat']))
                self.plot_data['lon'].append(float(new_display_data['lon']))
                self.plot_data['speed'].append(float(new_display_data['speed']))
                self.plot_data['course'].append(float(new_display_data['course']))
                self.plot_data['satellites'].append(float(new_display_data['satellites']))
                self.plot_data['altitude'].append(float(new_display_data['altitude']))
            except ValueError:
                for key in ['lat', 'lon', 'speed', 'course', 'satellites', 'altitude']:
                    self.plot_data[key].append(float('nan'))

            # 关键修复：同步截断所有数组
            current_length = len(self.plot_data['time'])
            if current_length > self.max_plot_points:
                # 计算需要截断的起始位置（保留最后max_plot_points个数据）
                truncate_start = current_length - self.max_plot_points
                for key in self.plot_data:
                    # 对每个数组执行同步截断
                    self.plot_data[key] = self.plot_data[key][truncate_start:]

            # 更新显示标签
            for key in new_display_data:
                self.data_values[key].setText(new_display_data[key])
            self.last_display_data = new_display_data.copy()
            self.last_update_time = current_time  # 更新时间戳

    def on_data_received(self, data: str):
        """处理接收到的数据"""
        if not self.is_receiving:
            return

        # 增加逻辑判断，只有按下连接按钮且自动保存开启时才统计数据量
        if self.serial_receiver and self.serial_receiver.is_connected and self.auto_save_enabled:
            # 计算KB和字节数
            kb = self.bytes_written // 1024
            bytes_total = self.bytes_written
            # 更新显示文本和工具提示（优化：仅内容变化时更新）
            self.data_size_label.setText(f"{kb} KB")
            new_tooltip = f"已记录：{kb} KB（{bytes_total} 字节）"
            if self.data_size_label.toolTip() != new_tooltip:  # 关键修改
                self.data_size_label.setToolTip(new_tooltip)
        else:
            # 若不满足条件，重置数据量显示和工具提示（同样优化）
            self.data_size_label.setText("0KB")
            new_tooltip = "已记录：0 KB（0 字节）"
            if self.data_size_label.toolTip() != new_tooltip:  # 关键修改
                self.data_size_label.setToolTip(new_tooltip)

        # 写入文件
        if self.auto_save_enabled and self.current_log_file and self.serial_receiver and self.serial_receiver.is_connected:
            self.file_write_buffer += data
            if len(self.file_write_buffer) >= self.file_write_threshold:
                try:
                    self.current_log_file.write(self.file_write_buffer)
                    self.current_log_file.flush()
                    self.bytes_written += len(self.file_write_buffer.encode('utf-8'))
                    self.file_write_buffer = ""

                    if self.bytes_written >= self.max_file_size:
                        self.create_new_log_file(self.serial_receiver.config.port)
                except Exception as e:
                    print(f"写入文件时出错: {str(e)}")
                    QMessageBox.critical(self, "错误", f"写入文件时出错: {str(e)}")
                    self.auto_save_enabled = False
                    if self.current_log_file:
                        self.current_log_file.close()
                        self.current_log_file = None

        # 更新数据缓冲区
        self.data_buffer += data
        if len(self.data_buffer) > self.max_buffer_length:
            self.data_buffer = self.data_buffer[-self.max_buffer_length:]

        # 解析数据
        if self.serial_receiver:
            parsed_data = self.serial_receiver.parse_nmea_data(data)
            if parsed_data:
                self.parsed_data_buffer += parsed_data + '\n'
                if len(self.parsed_data_buffer) > self.max_display_length:
                    self.parsed_data_buffer = self.parsed_data_buffer[-self.max_display_length:]

    def create_new_log_file(self, port_name: str):
        """创建新的日志文件"""
        if self.current_log_file and not self.current_log_file.closed:
            self.current_log_file.close()

        clean_port_name = port_name.replace('/', '_').replace('\\', '_').replace(':', '')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        baudrate = self.baudrate_combo.currentText()

        filename = f"{self.log_dir}/{clean_port_name}_{baudrate}_{timestamp}.txt"
        try:
            self.current_log_file = open(filename, 'a', encoding='utf-8')
            self.bytes_written = 0
            self.filename_label.setText(os.path.basename(filename))
        except IOError as e:
            print(f"无法创建日志文件: {str(e)}")
            QMessageBox.critical(self, "错误", f"无法创建日志文件: {str(e)}")
            self.auto_save_enabled = False
            self.filename_label.setText("未保存")

    def toggle_auto_save(self, state):
        """切换自动保存状态"""
        self.auto_save_enabled = (state == Qt.Checked)
        if self.auto_save_enabled and self.serial_receiver and self.serial_receiver.is_connected:
            self.create_new_log_file(self.serial_receiver.config.port)
        elif not self.auto_save_enabled and self.current_log_file:
            self.current_log_file.close()
            self.current_log_file = None
            self.filename_label.setText("未保存")

    def toggle_connection(self):
        """切换连接状态"""
        if self.serial_receiver and self.serial_receiver.is_connected:
            self.disconnect_serial()
        else:
            self.connect_serial()

    def connect_serial(self):
        """连接串口"""
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, "警告", "请选择串口")
            return

        # 检查串口是否存在（修复关键）
        available_ports = SerialReceiver.get_available_ports()
        available_devices = [device for device, _ in available_ports]  # 提取所有可用设备名
        if port not in available_devices:
            QMessageBox.critical(self, "错误", "所选串口不存在")
            return

        baudrate = self.baudrate_combo.currentText()

        try:
            config = SerialConfig(
                port=port,
                baudrate=int(baudrate))

            # 断开现有连接
            if self.serial_receiver:
                self.serial_receiver.disconnect()

            # 创建新日志文件
            if self.auto_save_enabled:
                self.create_new_log_file(port)

            # 创建接收器
            self.serial_receiver = SerialReceiver(config, self.port_index)
            self.serial_receiver.data_received.connect(self.on_data_received)
            self.serial_receiver.error_occurred.connect(self.on_serial_error)
            self.serial_receiver.connection_established.connect(lambda: self.connection_state_changed.emit())
            self.serial_receiver.start()

            self.connect_btn.setText("断开")
            self.port_combo.setEnabled(False)
            self.baudrate_combo.setEnabled(False)
            self.details_btn.setEnabled(True)
            # 已有：触发状态变化信号
            self.connection_state_changed.emit()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"连接错误: {str(e)}")

    def disconnect_serial(self):
        """断开串口连接"""
        if self.serial_receiver:
            self.serial_receiver.disconnect()
            self.serial_receiver = None

        self.connect_btn.setText("连接")
        self.port_combo.setEnabled(True)
        self.baudrate_combo.setEnabled(True)
        self.details_btn.setEnabled(False)

        # 关闭日志文件
        if self.current_log_file and not self.current_log_file.closed:
            self.current_log_file.close()
            self.current_log_file = None

        # 清空解析数据和内存缓存数据
        self.data_buffer = ""
        self.parsed_data_buffer = ""
        self.file_write_buffer = ""

        # 更新数据量显示
        self.data_size_label.setText("0KB")

        # 清空数据显示
        for value in self.data_values.values():
            value.setText("-")

        # 清空绘图数据存储
        for key in self.plot_data:
            self.plot_data[key].clear()

        # 关键新增：触发连接状态变化信号
        self.connection_state_changed.emit()

    def on_serial_error(self, error_msg: str):
        """处理串口错误"""
        QMessageBox.critical(self, "错误", error_msg)
        self.disconnect_serial()

    def update_port_tooltip(self):
        """更新串口选择框的工具提示更新（显示当前选中的完整设备信息）"""
        current_index = self.port_combo.currentIndex()
        if current_index != -1:
            # 获取当前选项的完整描述（通过ToolTipRole获取）
            full_info = self.port_combo.itemData(current_index, Qt.ToolTipRole)
            if self.port_combo.toolTip() != full_info:  # 关键修改
                self.port_combo.setToolTip(full_info)
        else:
            if self.port_combo.toolTip() != "":  # 关键修改
                self.port_combo.setToolTip("") 

    def show_port_details(self):
        """显示详情窗口"""
        if not self.serial_receiver or not self.serial_receiver.is_connected:
            return

        # 创建详情窗口
        self.detail_window = PortDataWindow(self.serial_receiver.config.port, self)
        self.detail_window.set_data(self.data_buffer)
        self.detail_window.show()

    def closeEvent(self, event):
        """清理资源"""
        self.disconnect_serial()
        if hasattr(self, 'detail_window'):
            self.detail_window.close()
        event.accept()


class PortDataWindow(QMainWindow):
    """串口数据详情窗口"""

    def __init__(self, port_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"串口数据详情 - {port_name}")
        self.resize(800, 600)
        self.parent_widget = parent
        self.is_paused = False

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # 数据显示区域（关键修改）
        self.data_text = QTextEdit()
        self.data_text.setReadOnly(True)
        self.data_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 允许双向扩展
        self.data_text.setSizeAdjustPolicy(QTextEdit.AdjustToContents)  # 根据内容调整大小
        layout.addWidget(self.data_text)

        # 控制按钮
        btn_layout = QHBoxLayout()

        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self.clear_data)
        btn_layout.addWidget(self.clear_btn)

        # 修改保存按钮为暂停按钮
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)
        btn_layout.addWidget(self.pause_btn)

        layout.addLayout(btn_layout)

        # 设置定时器更新数据
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_data)
        self.update_timer.start(100)  # 100ms更新一次

    def set_data(self, data: str):
        """设置初始数据"""
        self.data_text.setPlainText(data)
        self.data_text.verticalScrollBar().setValue(
            self.data_text.verticalScrollBar().maximum()
        )

    def update_data(self):
        """更新窗口内的数据"""
        if self.is_paused:
            return

        if self.parent_widget and self.parent_widget.serial_receiver and self.parent_widget.serial_receiver.is_connected:
            # 记录滚动条当前位置和是否在最底部
            scroll_bar = self.data_text.verticalScrollBar()
            at_bottom = scroll_bar.value() == scroll_bar.maximum()
            current_value = scroll_bar.value()

            # 更新数据
            new_data = self.parent_widget.data_buffer
            self.data_text.setPlainText(new_data)

            # 恢复滚动条位置
            if at_bottom:
                scroll_bar.setValue(scroll_bar.maximum())
            else:
                scroll_bar.setValue(current_value)

    def clear_data(self):
        """清空数据"""
        self.data_text.clear()

    def toggle_pause(self):
        """切换暂停状态"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.setText("继续")
        else:
            self.pause_btn.setText("暂停")

    def save_data(self):
        """保存数据到文件"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存串口数据",
            "",
            "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.data_text.toPlainText())
                QMessageBox.information(self, "成功", "数据保存成功")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")


class SerialReceiverApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多串口数据接收器")
        self.resize(1600, 1200)  # 调整窗口大小


        # 创建界面
        self.init_ui()

    def init_ui(self):
        # 主窗口布局
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        if getattr(sys, 'frozen', False):
            # 打包环境：使用PyInstaller临时目录中的资源
            icon_path = os.path.join(sys._MEIPASS, 'icon', 'app_window.svg')
        else:
            # 开发环境：使用项目根目录下的相对路径
            icon_path = os.path.join('icon', 'app_window.svg')
        self.setWindowIcon(QIcon(icon_path))

        # 第一行：控制按钮和标题
        first_row = QWidget()
        first_row_layout = QHBoxLayout(first_row)
        first_row_layout.setContentsMargins(0, 0, 0, 0)

        # 控制按钮组
        control_group = QGroupBox()
        control_layout = QHBoxLayout(control_group)
        control_layout.setContentsMargins(5, 5, 5, 5)

        self.refresh_btn = QPushButton("刷新可用串口")
        self.refresh_btn.setFixedWidth(120)
        self.refresh_btn.clicked.connect(self.refresh_all)
        control_layout.addWidget(self.refresh_btn)

        first_row_layout.addWidget(control_group)

        # 标题区域 - 使用与数据行相同的布局
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(5, 5, 5, 5)
        title_layout.setSpacing(10)

        # 添加占位控件以对齐串口控件布局
        title_layout.addWidget(QLabel(""))  # 串口号占位
        title_layout.addWidget(QLabel(""))  # 串口选择占位
        title_layout.addWidget(QLabel(""))  # 波特率占位
        title_layout.addWidget(QLabel(""))  # 连接按钮占位
        title_layout.addWidget(QLabel(""))  # 自动保存占位
        title_layout.addWidget(QLabel(""))  # 数据量占位

        # 创建标题标签
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)

        titles = ["时间", "纬度", "经度", "速度", "航向", "卫星", "海拔"]
        for title in titles:
            title_label = QLabel(title)
            title_label.setFixedWidth(107)
            title_label.setAlignment(Qt.AlignCenter)
            title_label.setFont(title_font)
            title_label.setStyleSheet("color: white;")
            title_layout.addWidget(title_label)

        first_row_layout.addWidget(title_widget, stretch=1)
        main_layout.addWidget(first_row)

        # 串口显示区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        self.port_container = QWidget()
        self.port_layout = QVBoxLayout(self.port_container)
        self.port_layout.setContentsMargins(0, 0, 0, 0)
        self.port_layout.setSpacing(10)

        # 创建8个串口控件（从1开始编号）
        self.port_widgets = []
        for i in range(1, 9):
            port_widget = SerialPortWidget(i)
            # 新增：监听串口状态变化信号
            port_widget.connection_state_changed.connect(self.update_port_select)
            self.port_widgets.append(port_widget)
            self.port_layout.addWidget(port_widget)

            # 添加分隔线（最后一个不添加）
            if i < 8:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                line.setStyleSheet("color: #eee;")
                self.port_layout.addWidget(line)

        scroll_area.setWidget(self.port_container)
        main_layout.addWidget(scroll_area, stretch=1)

        # 添加绘图组件到主布局底部
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')  # 设置背景为白色
        self.plot_widget.setLabel('left', 'Y轴值')
        self.plot_widget.setLabel('bottom', '时间（秒）')
        self.legend = self.plot_widget.addLegend()
        # 初始隐藏绘图区域
        

        # 绘图区域控制部分
        plot_control_container = QWidget()
        plot_control_layout = QHBoxLayout(plot_control_container)
        plot_control_layout.setContentsMargins(0, 5, 10, 5)

        # 参数选择框
        self.param_combo = QComboBox()
        self.param_combo.setFixedWidth(150)
        self.param_combo.addItems(['纬度', '经度', '速度(节)', '航向(°)', '卫星数', '海拔(m)'])
        self.param_combo.currentIndexChanged.connect(self.update_plot)
        plot_control_layout.addWidget(self.param_combo)

        # 串口勾选框组 - 直接初始化8个勾选框
        self.port_checkbox_container = QWidget()
        self.port_checkbox_layout = QHBoxLayout(self.port_checkbox_container)
        self.port_checkbox_layout.setContentsMargins(5, 0, 5, 0)  # 调整左右边距为5，更紧凑
        self.port_checkbox_layout.setSpacing(8)  # 缩小勾选框间距
        self.port_checkboxes = {}  # 保存串口勾选框引用
        
        
        
        # 移除原伸缩因子，使勾选框自然靠左紧凑
        # self.port_checkbox_layout.addStretch()  # 注释掉多余的伸缩因子
        
        # 初始提示标签（调整样式使其不影响勾选框紧凑性）
        self.no_ports_label = QLabel("无连接的串口")
        self.no_ports_label.setStyleSheet("color: #666;")
        self.port_checkbox_layout.addWidget(self.no_ports_label)
        
        plot_control_layout.addWidget(self.port_checkbox_container)

        main_layout.addWidget(plot_control_container)
        main_layout.addWidget(self.plot_widget)


        self.setCentralWidget(main_widget)

        # 设置定时器更新绘图
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start(1000)  # 每秒更新一次

        # 初始化串口选择框
        self.update_port_select()
        self.plot_widget.hide()

    def update_port_select(self):
        """更新串口勾选框（保留已勾选状态，移除断开连接的串口勾选框）"""
        # 记录当前已存在的勾选框索引和勾选状态
        existing_checkboxes = {index: checkbox.isChecked() for index, checkbox in self.port_checkboxes.items()}
    
        # 清除提示标签（仅移除提示，不清除勾选框）
        if self.no_ports_label.parent() is not None:
            self.no_ports_label.setParent(None)
    
        # 获取当前所有已连接的串口索引
        connected_ports = [i for i, widget in enumerate(self.port_widgets, start=1) 
                          if widget.serial_receiver and widget.serial_receiver.is_connected]

        # 移除已断开连接的串口对应的勾选框
        for index in list(self.port_checkboxes.keys()):
            if index not in connected_ports:
                self.port_checkbox_layout.removeWidget(self.port_checkboxes[index])
                self.port_checkboxes[index].setParent(None)
                del self.port_checkboxes[index]
    
        # 添加新连接的串口勾选框（仅添加不存在的）
        for port_index in connected_ports:
            if port_index not in self.port_checkboxes:
                checkbox = QCheckBox(f"串口{port_index}")
                checkbox.setChecked(False)  # 新添加默认未勾选
                checkbox.stateChanged.connect(self.update_plot)
                self.port_checkboxes[port_index] = checkbox
                self.port_checkbox_layout.addWidget(checkbox)
    
        # 恢复原有勾选框的勾选状态
        for index, checkbox in self.port_checkboxes.items():
            if index in existing_checkboxes:
                checkbox.setChecked(existing_checkboxes[index])
    
        # 处理无连接串口的提示
        if not connected_ports:
            self.no_ports_label = QLabel("无连接的串口")
            self.port_checkbox_layout.addWidget(self.no_ports_label)
            
        self.update_plot()

    def refresh_all(self):
        for widget in self.port_widgets:
            widget.refresh_ports()
        self.update_port_select()

    def clear_all(self):
        for widget in self.port_widgets:
            widget.data_buffer = ""
            widget.parsed_data_buffer = ""
            widget.file_write_buffer = ""
            widget.data_size_label.setText("0KB")
            for value in widget.data_values.values():
                value.setText("-")

    def update_plot(self):
        """更新绘图内容"""
        self.plot_widget.clear()  # 清空旧数据
        
        # 获取选中的参数
        selected_param = self.param_combo.currentText()
        
        # 参数映射
        param_map = {
            '纬度': 'lat',
            '经度': 'lon',
            '速度(节)': 'speed',
            '航向(°)': 'course',
            '卫星数': 'satellites',
            '海拔(m)': 'altitude'
        }
        
        param_key = param_map.get(selected_param)

        
        # 定义颜色列表
        colors = ['#FF0000', '#00FF00', '#0000FF', '#FFA500', '#800080', '#008080', '#FF00FF', '#00FFFF']
        
        # 绘制每个选中的串口数据
        for i, widget in enumerate(self.port_widgets):
            port_num = i + 1
            if port_num in self.port_checkboxes and self.port_checkboxes[port_num].isChecked():
                if widget.serial_receiver and widget.serial_receiver.is_connected:
                    # 获取该串口的绘图数据
                    time_data = widget.plot_data['time']
                    param_data = widget.plot_data[param_key]
                    
                    if time_data and param_data:
                        # 新增：检查并截断数据长度，确保X和Y数组长度一致
                        min_len = min(len(time_data), len(param_data))
                        time_data = time_data[:min_len]  # 截断时间数据
                        param_data = param_data[:min_len]  # 截断参数数据

                        color = colors[i % len(colors)]
                        self.plot_widget.plot(
                            time_data, param_data,
                            name=f"串口{port_num}",
                            pen=pg.mkPen(color=color, width=2))
        
        # 更新坐标轴标签
        self.plot_widget.setLabel('left', selected_param)
        self.plot_widget.setLabel('bottom', '时间（秒）')

        # 新增：根据勾选状态控制绘图区域显示/隐藏
        has_checked = any(checkbox.isChecked() for checkbox in self.port_checkboxes.values())
        if has_checked:
            self.plot_widget.show()
        else:
            self.plot_widget.hide()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SerialReceiverApp()
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5'))
    window.show()
    sys.exit(app.exec_())
