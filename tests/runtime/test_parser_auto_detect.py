from pyquipu.runtime.parser import detect_best_parser


class TestAutoDetect:
    def test_detect_backtick_simple(self):
        text = """
```act
write_file
```
"""
        assert detect_best_parser(text) == "backtick"

    def test_detect_tilde_simple(self):
        text = """
~~~act
write_file
~~~
"""
        assert detect_best_parser(text) == "tilde"

    def test_detect_variable_length_tilde(self):
        """测试变长波浪号"""
        text = """
~~~~~act
write_file
~~~~~
"""
        assert detect_best_parser(text) == "tilde"

    def test_detect_variable_length_backtick(self):
        """测试变长反引号"""
        text = """
````act
write_file
````
"""
        assert detect_best_parser(text) == "backtick"

    def test_detect_with_interference(self):
        """测试文档前言中包含代码块，但不含 act 关键字，应忽略"""
        # 注意：这里去掉了缩进，模拟真实的 Markdown 文件
        text = """
Here is some example code:
```python
print("hello")
```

Now the real instruction:
~~~act
write_file
~~~
"""
        assert detect_best_parser(text) == "tilde"

    def test_detect_first_act_wins(self):
        """测试以第一个出现的 act 块为准"""
        text = """
```act
first_op
```

~~~act
second_op
~~~
"""
        assert detect_best_parser(text) == "backtick"

    def test_default_fallback(self):
        """如果没有 act 块，默认回退到 backtick"""
        text = "Just some text with no acts."
        assert detect_best_parser(text) == "backtick"

    def test_case_insensitivity(self):
        text = """
~~~ACT
write_file
~~~
"""
        assert detect_best_parser(text) == "tilde"
