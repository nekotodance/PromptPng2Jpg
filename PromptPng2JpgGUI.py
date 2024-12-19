import sys
import os
import time
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, QTimer
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QListWidget, QStatusBar
from PIL import Image
import PromptPng2Jpg
import pvsubfunc

# 設定ファイル
SETTINGS_FILE = "PromptPng2JpgGUI_settings.json"
GEOMETRY_X = "geometry-x"
GEOMETRY_Y = "geometry-y"
GEOMETRY_W = "geometry-w"
GEOMETRY_H = "geometry-h"
JPG_QUALITY = "setting-jpgquality"
THREADS_NUM = "setting-threadsnum"

# マルチスレッド用ワーカークラス
#T.B.C.:色々試したがプログレスバーの表示がどうにもうまく行かない。保留。
class Worker(QRunnable):
    def __init__(self, file_path, quality, on_complete):
        super().__init__()
        self.file_path = file_path
        self.quality = quality
        self.on_complete = on_complete
        self._is_cancelled = False

    def run(self):
        # 画像の変換処理
        try:
            if self._is_cancelled:
                return  # キャンセルされた場合は処理を終了
            with Image.open(self.file_path) as img:
                if img.format == 'PNG':
                    jpg_path = self.file_path.rsplit('.', 1)[0] + '.jpg'
                    PromptPng2Jpg.convert_to_jpg(self.file_path,os.path.dirname(self.file_path),self.quality)
                    #ログ出力をすると2割くらい処理時間が増えるので止める
                    #print(f"Converted {self.file_path} to {jpg_path}")
                    if self._is_cancelled:
                        return  # キャンセルされた場合は処理を終了
                    self.on_complete(True)
                else:
                    print(f"Skipping non-PNG file: {self.file_path}")
                    if self._is_cancelled:
                        return  # キャンセルされた場合は処理を終了
                    self.on_complete(False)
        except Exception as e:
            print(f"Error converting {self.file_path}: {e}")
            if self._is_cancelled:
                return  # キャンセルされた場合は処理を終了
            self.on_complete(False)

    def cancel(self):
        self._is_cancelled = True

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.jpgquality = 85  # デフォルトのJPEG品質
        self.threadsnum = 11  # デフォルトのスレッド数

        self.setWindowTitle('PNG to JPG Converter')
        self.setGeometry(100, 100, 640, 480)
        # 設定ファイルが存在しない場合初期値で作成する
        if not os.path.exists(SETTINGS_FILE):
            self.createSettingFile()
        # 起動時にウィンドウ設定を復元
        self.load_settings()

        self.setAcceptDrops(True)

        # UIの設定
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)

        self.layout = QVBoxLayout(self.centralWidget)

        self.label = QLabel('Drag and Drop PNG files or folders here.')
        self.layout.addWidget(self.label)

        self.fileListWidget = QListWidget()
        self.layout.addWidget(self.fileListWidget)

        # 設定値レイアウト（横並び）
        self.settingLayout = QHBoxLayout()
        # JPG品質設定のラベルとスピンボックス
        self.settingLayout.addWidget(QLabel('JPG Quality def:85'))
        self.qualitySpinBox = QSpinBox()
        self.qualitySpinBox.setMinimum(1)  # 最小1
        self.qualitySpinBox.setMaximum(100)  # 最大100
        self.qualitySpinBox.setValue(self.jpgquality)  # 初期値85（JPG品質としても使用）
        self.settingLayout.addWidget(self.qualitySpinBox)
        # スレッド数設定のラベルとスピンボックス
        self.settingLayout.addWidget(QLabel('Number of Threads'))
        self.threadSpinBox = QSpinBox()
        self.threadSpinBox.setMinimum(1)
        self.threadSpinBox.setMaximum(os.cpu_count())  # 最大PCのCPUコア数
        self.threadSpinBox.setValue(self.threadsnum)  # デフォルト値はCPUコア数-1
        self.settingLayout.addWidget(self.threadSpinBox)
        self.layout.addLayout(self.settingLayout)

        # ボタンレイアウト（横並び）
        self.buttonLayout = QHBoxLayout()
        # 変換ボタン
        self.convertButton = QPushButton('Convert')
        self.convertButton.setFixedHeight(40)  # ボタンの高さを調整
        self.buttonLayout.addWidget(self.convertButton)
        # キャンセルボタン
        self.cancelButton = QPushButton('Cancel')
        self.cancelButton.setFixedHeight(40)  # ボタンの高さを調整
        self.cancelButton.setEnabled(False)  # 初期状態では無効化
        self.buttonLayout.addWidget(self.cancelButton)
        self.layout.addLayout(self.buttonLayout)

        # ステータスバーを追加
        self.statusBar = QStatusBar()
        self.statusBar.setStyleSheet("color: white; font-size: 14px; background-color: #31363b;")
        self.setStatusBar(self.statusBar)

        self.convertButton.clicked.connect(self.start_conversion)
        self.cancelButton.clicked.connect(self.cancel_conversion)

        # スピンボックスの値変更時に値を更新
        self.qualitySpinBox.valueChanged.connect(self.update_jpgquality_values)
        self.threadSpinBox.valueChanged.connect(self.update_threadsnum_values)

        # スレッドプールの初期化
        self.thread_pool = QThreadPool()

        self.file_paths = []  # 変換するファイルのリスト
        self.converted_files = 0  # 変換したファイル数
        self.start_time = 0  # 変換開始時間

        self.workers = []  # Workerのリスト

    # アプリ終了時に位置とサイズ、設定値を保存する
    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    # 変換ボタン処理
    def start_conversion(self):
        # 変換ボタンが押されたときにファイルリストから変換処理を開始
        self.file_paths = [self.fileListWidget.item(i).text() for i in range(self.fileListWidget.count())]

        if not self.file_paths:
            self.statusBar.showMessage('No files to convert.')
            return

        self.converted_files = 0
        self.start_time = time.time()  # 変換開始時刻

        self.cancelButton.setEnabled(True)  # キャンセルボタンを有効化
        self.convertButton.setEnabled(False)  # 変換ボタンを無効化

        self.statusBar.showMessage('Converting...')
        self.convert_files(self.file_paths)

    # キャンセルボタン処理
    def cancel_conversion(self):
        # キャンセルボタンが押された場合、すべてのWorkerをキャンセル
        for worker in self.workers:
            worker.cancel()

        self.statusBar.showMessage('Conversion cancelled.')
        self.convertButton.setEnabled(True)
        self.cancelButton.setEnabled(False)

    # 変換処理
    def convert_files(self, file_paths):
        # スレッド数を指定して変換処理をマルチスレッドで行う
        num_threads = self.threadSpinBox.value()  # スレッド数の取得
        self.thread_pool.setMaxThreadCount(num_threads)  # スレッドプールの最大スレッド数を設定

        for file_path in file_paths:
            worker = Worker(file_path, self.jpgquality, self.on_complete)
            self.workers.append(worker)  # Workerをリストに追加
            self.thread_pool.start(worker)  # スレッドプールにタスクを追加

    # 完了時処理
    def on_complete(self, success):
        # 変換が完了した後に呼ばれるコールバック
        if success:
            self.converted_files += 1

        # すべてのファイルが変換されたか確認
        if self.converted_files == len(self.file_paths):
            elapsed_time = time.time() - self.start_time  # 経過時間
            self.statusBar.showMessage(f'Conversion complete! {self.converted_files} files converted in {elapsed_time:.2f} seconds.')
            self.convertButton.setEnabled(True)
            self.cancelButton.setEnabled(False)

    # 設定値更新時処理
    def update_jpgquality_values(self):
        # Jpg品質の値変更時に変数を更新
        self.jpgquality = self.qualitySpinBox.value()
    def update_threadsnum_values(self):
        # スレッド数の値変更時に変数を更新
        self.threadsnum = self.threadSpinBox.value()

    # ドラッグエンター
    def dragEnterEvent(self, event: QDragEnterEvent):
        event.acceptProposedAction()

    # ドラッグ＆ドロップ時
    def dropEvent(self, event: QDropEvent):
        file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
        all_files = []

        # ドラッグ＆ドロップで受け取ったファイルまたはフォルダの処理
        for path in file_paths:
            if os.path.isdir(path):  # フォルダの場合
                all_files.extend(self.get_png_files_in_folder(path))
            elif path.lower().endswith('.png'):  # PNGファイルの場合
                all_files.append(path)

        if all_files:
            self.fileListWidget.clear()  # リストをクリア
            self.fileListWidget.addItems(all_files)  # リストに追加

        self.statusBar.showMessage(f'Droped {len(all_files)} files.')

    def get_png_files_in_folder(self, folder_path):
        # フォルダ内の全てのPNGファイルを再帰的に取得
        png_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith('.png'):
                    #png_files.append(os.path.join(root, file))
                    png_files.append(root + "/" + file) #ファイルのドラッグドロップ時のパスセパレータに合わせる
        return png_files

    #設定ファイルの初期値作成
    def createSettingFile(self):
        self.save_settings()

    #設定ファイルの読込
    def load_settings(self):
        self.jpgquality = int(str(pvsubfunc.read_value_from_config(SETTINGS_FILE, JPG_QUALITY)))
        if self.jpgquality < 1 or self.jpgquality > 100:
            self.jpgquality = 85
        self.threadsnum = int(str(pvsubfunc.read_value_from_config(SETTINGS_FILE, THREADS_NUM)))
        if self.threadsnum < 1 or self.threadsnum > os.cpu_count():
            self.threadsnum = os.cpu_count() - 1
            if self.threadsnum < 1:
                self.threadsnum = 1 #今どき、1スレッドのCPUはないでしょうけど念の為

        #self.setGeometry(100, 100, 640, 480)    #位置とサイズ
        geox = pvsubfunc.read_value_from_config(SETTINGS_FILE, GEOMETRY_X)
        geoy = pvsubfunc.read_value_from_config(SETTINGS_FILE, GEOMETRY_Y)
        geow = pvsubfunc.read_value_from_config(SETTINGS_FILE, GEOMETRY_W)
        geoh = pvsubfunc.read_value_from_config(SETTINGS_FILE, GEOMETRY_H)
        if any(val is None for val in [geox, geoy, geow, geoh]):
            self.setGeometry(0, 0, 640, 480)    #位置とサイズ
        else:
            self.setGeometry(geox, geoy, geow, geoh)    #位置とサイズ

    #設定ファイルの保存
    def save_settings(self):
        pvsubfunc.write_value_to_config(SETTINGS_FILE, JPG_QUALITY, self.jpgquality)
        pvsubfunc.write_value_to_config(SETTINGS_FILE, THREADS_NUM, self.threadsnum)

        pvsubfunc.write_value_to_config(SETTINGS_FILE, GEOMETRY_X, self.geometry().x())
        pvsubfunc.write_value_to_config(SETTINGS_FILE, GEOMETRY_Y, self.geometry().y())
        pvsubfunc.write_value_to_config(SETTINGS_FILE, GEOMETRY_W, self.geometry().width())
        pvsubfunc.write_value_to_config(SETTINGS_FILE, GEOMETRY_H, self.geometry().height())

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
