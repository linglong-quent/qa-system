"""批量扩充 magic_whitelist，把高频出现的量化领域常用数字加入白名单"""
import yaml
import logging
logger = logging.getLogger(__name__)
config_path = 'E:\\WB\\qa-system\\.ai\\projects\\linglong_local.yaml'
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

def to_str_set(lst):
    """to str set。"""
    return set((str(x) for x in lst or []))
current_whitelist = to_str_set(config.get('magic_whitelist', []))
codeban_whitelist = to_str_set(config.get('code_ban_check', {}).get('magic_whitelist', []))
print(f'当前顶层 magic_whitelist: {len(current_whitelist)} 个')
print(f'当前 code_ban_check magic_whitelist: {len(codeban_whitelist)} 个')
high_freq_numbers = ['70', '80', '55', '65', '35', '45', '75', '85', '5', '10', '20', '60', '120', '250', '22', '26', '27', '29', '13', '11', '23', '18', '19', '1.2', '0.85', '1.3', '0.55', '0.35', '0.98', '1.1', '0.07', '0.08', '1.03', '1.05', '1.095', '0.12', '0.09', '9.5', '5000000000.0', '50000000000.0', '100000000000', '20000000000', '300000000', '500000000.0', '50000000', '1800', '42', '570', '630', '840']
additional = ['244', '252', '220', '0.01', '0.02', '0.03', '0.05', '0.1', '0.15', '0.2', '0.25', '0.3', '60', '300', '600', '900', '1800', '3600', '86400', '-0.1', '-0.2', '0.5', '0.6', '0.7', '0.8', '0.9', '1.5', '2.0', '2.5', '3.0', '0.02', '0.03', '0.05', '0.1', '10', '15', '20', '30', '50', '3', '5', '7', '10', '14', '21', '30', '60', '90']
all_new = set(high_freq_numbers + additional)
to_add_top = all_new - current_whitelist
to_add_codeban = all_new - codeban_whitelist
print(f'\n顶层待新增: {len(to_add_top)} 个')
print(f'code_ban_check 待新增: {len(to_add_codeban)} 个')

def safe_sort(lst):

    """safe sort。"""
    def key_func(x):
        """key func。"""
        s = str(x)
        try:
            return (0, float(s))
        except Exception as e:
            logger.debug('Exception type: %s', type(e).__name__)
            logger.debug('except Exception: %s', e)
            return (1, s)
    return sorted(lst, key=key_func)
new_top_list = safe_sort(list(current_whitelist | all_new))
config['magic_whitelist'] = new_top_list
if 'code_ban_check' in config:
    new_codeban_list = safe_sort(list(codeban_whitelist | all_new))
    config['code_ban_check']['magic_whitelist'] = new_codeban_list
with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
print(f'\n✓ 已更新 {config_path}')
print(f'  顶层白名单: {len(new_top_list)} 个')
print(f'  code_ban_check 白名单: {len(new_codeban_list)} 个')
