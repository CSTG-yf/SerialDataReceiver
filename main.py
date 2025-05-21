import serial
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


class SerialPortWidget(QWidget):
    """单个串口控件，带标题的紧凑布局"""

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

        for value in self.data_values.values():
            value.setAlignment(Qt.AlignCenter)  # 居中对齐
            value.setStyleSheet("""
                QLabel {
                    padding: 2px;
                    border: 1px solid #eee;
                    border-radius: 3px;
                    background: #f8f8f8;
                }
            """)

        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)

        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setHorizontalSpacing(5)

        # 串口标识（原50→40）
        self.port_label = QLabel(f"串口{self.port_index}")
        self.port_label.setFixedWidth(40)
        self.port_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.port_label, 0, 0)

        # 串口选择（原120→100）
        self.port_combo = QComboBox()
        self.port_combo.setFixedWidth(100)
        self.refresh_ports()
        layout.addWidget(self.port_combo, 0, 1)

        # 波特率选择（原80→70）
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        self.baudrate_combo.setCurrentText('9600')
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
        layout.addWidget(self.filename_label, 0, 5, 1, 1)  # 添加伸缩因子，让标签能扩展

        # 数据量显示
        self.data_size_label = QLabel("0KB")
        self.data_size_label.setFixedWidth(50)
        layout.addWidget(self.data_size_label, 0, 6)

        # 数据值显示区域（关键修改）
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
                }
            """)
            layout.addWidget(value, 0, col)
            layout.setColumnStretch(col, 1)  # 设置列拉伸因子，允许自动扩展

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
        """刷新可用串口列表"""
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = SerialReceiver.get_available_ports()
        self.port_combo.addItems(ports)
        if current_port in ports:
            self.port_combo.setCurrentText(current_port)

    def update_display(self):
        """更新数据显示"""
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

        # 打印解析数据中的时间
       

        # 记录上一次显示的数据
        if not hasattr(self, 'last_display_data'):
            self.last_display_data = {}

        # 仅在数据有更新时才更新显示
        if new_display_data != self.last_display_data:
            for key in new_display_data:
                self.data_values[key].setText(new_display_data[key])  # 改为QLabel的setText
            self.last_display_data = new_display_data.copy()

    def on_data_received(self, data: str):
        """处理接收到的数据"""
        if not self.is_receiving:
            return

        # 增加逻辑判断，只有按下连接按钮且自动保存开启时才统计数据量
        if self.serial_receiver and self.serial_receiver.is_connected and self.auto_save_enabled:
            # 更新数据量显示（修改此处：使用实际写入的字节数）
            self.data_size_label.setText(f"{self.bytes_written // 1024} KB")
        else:
            # 若不满足条件，重置数据量显示
            self.data_size_label.setText("0KB")

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
                self.parsed_data_buffer += parsed_data + "\n"
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

        # 检查串口是否存在
        available_ports = SerialReceiver.get_available_ports()
        if port not in available_ports:
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
            self.serial_receiver.start()

            self.connect_btn.setText("断开")
            self.port_combo.setEnabled(False)
            self.baudrate_combo.setEnabled(False)
            self.details_btn.setEnabled(True)

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

    def on_serial_error(self, error_msg: str):
        """处理串口错误"""
        QMessageBox.critical(self, "错误", error_msg)
        self.disconnect_serial()

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
        self.resize(1600, 800)  # 调整窗口大小

        # 创建界面
        self.init_ui()

    def init_ui(self):
        # 主窗口布局
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)

        # 第一行：控制按钮和标题
        first_row = QWidget()
        first_row_layout = QHBoxLayout(first_row)
        first_row_layout.setContentsMargins(0, 0, 0, 0)

        # 控制按钮组
        control_group = QGroupBox()
        control_layout = QHBoxLayout(control_group)
        control_layout.setContentsMargins(5, 5, 5, 5)

        self.refresh_btn = QPushButton("刷新所有串口")
        self.refresh_btn.setFixedWidth(120)
        self.refresh_btn.clicked.connect(self.refresh_all)
        control_layout.addWidget(self.refresh_btn)

        self.clear_all_btn = QPushButton("清空所有数据")
        self.clear_all_btn.setFixedWidth(120)
        self.clear_all_btn.clicked.connect(self.clear_all)
        control_layout.addWidget(self.clear_all_btn)

        first_row_layout.addWidget(control_group)

        # 标题区域 - 使用与数据行相同的布局
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(5, 5, 5, 5)
        title_layout.setSpacing(10)

        # 添加占位控件以对齐串口控件布局
        title_layout.addWidget(QLabel(""))  # 串口号占位
        title_layout.addWidget(QLabel(""))  # 串口选择占位
        # 移除刷新按钮占位
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
            title_label.setFixedWidth(112)
            title_label.setAlignment(Qt.AlignCenter)
            title_label.setFont(title_font)
            title_label.setStyleSheet("color: #666;")
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

        self.setCentralWidget(main_widget)

    def refresh_all(self):
        """刷新所有串口"""
        for widget in self.port_widgets:
            widget.refresh_ports()

    def clear_all(self):
        """清空所有数据"""
        for widget in self.port_widgets:
            widget.data_buffer = ""
            widget.parsed_data_buffer = ""
            widget.data_size_label.setText("0 KB")

            # 清空数据显示
            for value in widget.data_values.values():
                value.setText("-")

    def closeEvent(self, event):
        """窗口关闭事件"""
        for widget in self.port_widgets:
            widget.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SerialReceiverApp()
    window.show()
    sys.exit(app.exec_())
