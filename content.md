## chore 脚本可以遍历指定目录下的所有文件，并将 "Axon" 替换为 "Quipu"

```act
write_file replace_axon.sh
```

```bash
#!/bin/bash

# --- 配置 ---
# 设置要搜索和替换的根目录，'.' 表示当前目录
# 你可以修改为 'src' 或其他任何目录
SEARCH_DIR="."

# 设置要处理的文件扩展名，用空格分隔
# 例如: "md py sh"
FILE_EXTENSIONS="md py"

# 要查找和替换的字符串
OLD_STRING="Axon"
NEW_STRING="Quipu"

# --- 脚本主体 ---

# 检查 sed 是否支持 -i '' 语法 (macOS) 或 -i (GNU/Linux)
# 这是为了实现跨平台的原地替换 (in-place edit)
SED_INPLACE_CMD="sed -i"
if [[ "$(uname)" == "Darwin" ]]; then
  SED_INPLACE_CMD="sed -i ''"
fi

echo "🚀 开始将 '$OLD_STRING' 替换为 '$NEW_STRING'..."
echo "🔍 搜索目录: $SEARCH_DIR"
echo "📄 文件类型: $FILE_EXTENSIONS"
echo "----------------------------------------"

# 构建 find 命令的文件名匹配模式
name_pattern=""
for ext in $FILE_EXTENSIONS; do
  if [ -z "$name_pattern" ]; then
    name_pattern="-name \"*.$ext\""
  else
    name_pattern="$name_pattern -o -name \"*.$ext\""
  fi
done

# 使用 find 找到所有匹配的文件，然后用 xargs 将它们传递给 sed 进行替换
# eval is used here to correctly handle the constructed name_pattern string
eval find "$SEARCH_DIR" \( $name_pattern \) -type f -print0 | while IFS= read -r -d '' file; do
    echo "Processing: $file"
    # 执行原地替换
    $SED_INPLACE_CMD "s/$OLD_STRING/$NEW_STRING/g" "$file"
done

echo "----------------------------------------"
echo "✅ 替换完成！"

```
