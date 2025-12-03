import importlib.util
import inspect
import sys
spec = importlib.util.spec_from_file_location('bot_rec', '__pycache__/bot.cpython-310.pyc')
module = importlib.util.module_from_spec(spec)
sys.modules['bot_rec'] = module
spec.loader.exec_module(module)
print('module loaded:', module)
print('has TradingLionsBot?', hasattr(module, 'TradingLionsBot'))
print(inspect.getsource(module.TradingLionsBot))
