import pandas as pd

# Читаем xls
df = pd.read_excel('6.xls', header=None)

# Сохраняем в CSV (разделитель ;, кодировка UTF-8)
df.to_csv('6_fixed.csv', sep=';', index=False, header=False, encoding='utf-8-sig')

print("✅ Конвертация завершена! Файл: 6_fixed.csv")