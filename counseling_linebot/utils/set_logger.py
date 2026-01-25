import logging
import logging.handlers
import socket
import yaml
import os
import re

from utils.ansi import *

# logディレクトリがない場合は作成
if not os.path.exists('log'):
    os.makedirs('log')
    print("Created log directory: log")

class CategoryFilter(logging.Filter):
    def __init__(self, allowed_categories):
        """
        allowed_categories の形式:
            INFO
                - 'data'
                - 'model'
            DEBUG: 
                - 'data'
                - 'model'
                - 'ui'
        """
        super().__init__()
        self.allowed_categories = allowed_categories

    def filter(self, record):
        """
        returnが True のときだけログを出力する
        DEBUG レベルのときだけカテゴリをチェックし、
        許可されたカテゴリに含まれている場合はログを出力する。
        """
        all_levels = {name: value for name, value in logging._nameToLevel.items()}
        # 各レベルの値を確認し、対応するカテゴリを取得
        for level_name, level_value in all_levels.items():
            if record.levelno == level_value:
                filter_category = self.allowed_categories.get(level_name, set())
                return self._filter(record, filter_category)

        return True

    def _filter(self, record, filter_category):
        record_attr = getattr(record, 'C', None)

        # カテゴリが指定されていて，かつ，許可されたカテゴリに含まれている場合はログを出力
        if (record_attr is not None) and (record_attr in filter_category):
            return True
        
        # カテゴリが指定されていない場合は，通常通り，ログを出力
        elif record_attr is None:
            return True
        
        else:
            return False


# --- カスタムログレベルを登録 ---
def register_custom_levels(custom_levels):
    for level in custom_levels:
        name = level["NAME"]
        value = level["VALUE"]
        if (name is None) or (value is None):
            continue

        # ログレベル名と値を登録
        logging.addLevelName(value, name)

        # ロガーにメソッドを追加
        def make_log_method(level_value, level_name):
            def log_method(self, message, *args, **kwargs):
                if self.isEnabledFor(level_value):
                    self._log(level_value, message, args, **kwargs)
            log_method.__name__ = level_name.lower()
            return log_method

        setattr(logging.Logger, name.lower(), make_log_method(value, name))    # これにより，logger.<name> で呼び出せるようになる
        setattr(logging, name.upper(), value)  # これにより，グローバルにログレベルを登録されるので，logging.<name> でログレベルの値を参照できるようになる



# ログレベルの判定と設定
def set_logger_level(logger, custom_levels, logger_level_name):
    
    # 標準ログレベル名と値の辞書を作成
    standard_levels = {name: value for name, value in logging._nameToLevel.items()}

    # 標準ログならそのまま設定
    if logger_level_name in standard_levels:
        logger.setLevel(standard_levels[logger_level_name])
        # print(f"Setting logger level to standard level: {logger_level_name} ({standard_levels[logger_level_name]})")
    
    # カスタムログレベルなら，ログレベルを参照し，設定
    else:
        # カスタムレベルを検索
        match = next((lvl for lvl in custom_levels if lvl["name"] == logger_level_name), None)
        if match:
            value = match["value"]
            logger.setLevel(value)
            # print(f"Setting logger level to custom level: {logger_level_name} ({value})")
        else:
            raise ValueError(f"Unknown log level: {logger_level_name}")
        
    return logger


# ─── インデント付きフォーマッタ ─────────────────────────────
class IndentFormatter(logging.Formatter):
    """
    2行目以降のプレフィックス幅を揃えて
    '\n' 後に自動で空白を挿入するFormatter
    """
    def __init__(self, fmt, datefmt=None, use_color=False, color_config=None):
        super().__init__(fmt=fmt, datefmt=datefmt, style='%')
        
        # 正規表現でフィールド名と幅を抽出
        pattern = r'%\((\w+)\)-(\d+)s'
        matches = re.findall(pattern, fmt)

        # 辞書に変換
        field_widths = {field: int(width) for field, width in matches}

        # filenameとfuncNameの幅を取得
        self.filename_width = field_widths.get('filename', 30)
        self.funcname_width = field_widths.get('funcName', 30)
        self.threadName_width = field_widths.get('threadName', 20)
        self.lineno_width = field_widths.get('lineno', 4)
        self.levelname_width = field_widths.get('levelname', 8)
        
        # 色付けオプション
        self.use_color = use_color
        self.color_config = color_config


    def format(self, record):
        record.filename = record.filename[:self.filename_width]
        record.funcName  = record.funcName[:self.funcname_width]
        record.threadName = record.threadName[:self.threadName_width]
        record.lineno = str(record.lineno).rjust(self.lineno_width)
        record.levelname = record.levelname[:self.levelname_width]
        
        log = super().format(record)   # log全体
        msg = record.getMessage()      # メッセージ部分のみ

        log_length = len(log) - len(msg)   # メッセージ部分を除いた長さ

        if log_length > 0:
            # 改行後に空白を挿入
            log = log.replace('\n', '\n' + ' ' * log_length)

        if self.use_color:
            log = highlight_log(log, self.color_config)  # 色付け
        else:
            ansi_pattern = re.compile(r'\033\[[0-9;]*m')
            log = ansi_pattern.sub('', log) 

        return log

class ColorFormatter(logging.Formatter):
    """
    コンソール用に色付けするフォーマッタ
    """
    def __init__(self, fmt, color_config=None):
        super().__init__(fmt=fmt)
        self.color_config = color_config

    def format(self, record):
        log = super().format(record)
        log = highlight_log(log, self.color_config)

        return log


# ─── ログの色付け関数 ──────────────────────────────────────
def highlight_log(log, color_config):
    for color, pattern_list in color_config.items():
        color_code = COLOR_DICT[color]
        if pattern_list is not None:
            for value in pattern_list:
                if isinstance(value, dict):
                    pattern = value['pattern']
                    group = value['group']
                else:
                    group = 0
                    pattern = value
                    
                if pattern is not None:
                    log = re.sub(pattern, 
                                 lambda m: m.group(0).replace(m.group(group), f"{color_code}{m.group(group)}{R}"), 
                                 log)
    return log



# ─── ロガー設定関数 ──────────────────────────────────────────
def setting_logger(config) -> logging.Logger:
    
    # configから設定値を取得
    logger_level = config['LOGGER_LEVEL'].upper()
    module_name = config['MODULE_NAME']
    user_color = config['USE_COLOR']
    color_config = config['COLOR_CONFIG']
    max_bytes = config['MAX_LOG_FILE_SIZE']
    max_bytes = int(eval(max_bytes))  # 数値に変換
    backup_count = config['BACKUP_COUNT']
    datefmt = config['DATE_FORMAT']
    fmt = config['LOG_FORMAT']
    use_console = config['USE_CONSOLE']
    enabled_categories = config['ENABLED_CATEGORIES']
    custom_levels = config['CUSTOM_LEVELS']
    use_pc_name = config.get('USE_PC_NAME', False)
    if use_pc_name:
        pc_name = socket.gethostname()
        # pc名ディレクトリがない場合は作成
        if not os.path.exists(f'log/{pc_name}'):
            os.makedirs(f'log/{pc_name}')
            print(f"Created log directory: log/{pc_name}")
        log_file_path = f'./log/{pc_name}/' + config['LOG_FILE_NAME'] + config['LOG_EXTENSION']
    else:
        log_file_path = './log/' + config['LOG_FILE_NAME'] + config['LOG_EXTENSION']
    
    # カスタムログレベルを登録
    if custom_levels != None:
        register_custom_levels(custom_levels)

    # ルート or モジュールロガー取得
    logger = logging.getLogger(module_name) if module_name else logging.getLogger()
    logger = set_logger_level(logger, custom_levels, logger_level)  # ログレベルの設定

    # フォーマット文字列の設定
    fh_fmt = fmt
    ch_fmt = '%(message)s'

    # ファイルハンドラ (サイズ・世代管理)
    fh = logging.handlers.RotatingFileHandler(
        filename=log_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    # fh.setLevel(logger_level)
    fh.setFormatter(IndentFormatter(fh_fmt + '%(message)s', datefmt, use_color=user_color, color_config=color_config))
    fh.addFilter(CategoryFilter(enabled_categories))
    logger.addHandler(fh)

    # コンソールハンドラ
    if use_console:
        ch = logging.StreamHandler()
        # ch.setLevel(logger_level)
        ch.setFormatter(ColorFormatter(ch_fmt, color_config=color_config))
        ch.addFilter(CategoryFilter(enabled_categories))
        logger.addHandler(ch)

    return logger


# ─── 起動用ラッパー ──────────────────────────────────────────
def start_logger(config_path) -> logging.Logger:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    module_name = config.get('MODULE_NAME', 'main')    

    # 既存のloggerを取得し，存在する場合は再利用
    logger = logging.getLogger(module_name)
    if logger.handlers:
        return logger

    logger = setting_logger(config)
    logger.info('#' * 30 + ' Starting the program ' + '#' * 30)
    return logger


# python -m utils.set_logger
if __name__ == "__main__":

    config_path = './config/logger/system.yaml'
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        exit()
    
    logger = start_logger(config_path)
    
    logger.info(f"{BG}(INFOMATION){R} Logger initialized with config: {config_path}")
    logger.debug(f"{BOLD}{MG}[DEBUG]{R} This is a debug message.\n{B}改行しました{R}")

    for color_name, color in COLOR_DICT.items():
        logger.info(f"{COLOR_DICT[color_name]}{color_name}{R}")
