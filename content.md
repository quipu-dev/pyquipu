# fix: 修复 TUI 测试中的构造函数参数缺失

## 用户需求
更新后的 `QuipuUiApp` 需要 `content_loader` 参数，导致现有 UI 测试因参数缺失而失败。需要更新测试代码以适配新的 API。

## 目标
1. 修复 `tests/test_ui_logic.py` 中的 `QuipuUiApp` 实例化。
2. 修复 `tests/test_ui_reachability.py` 中的 `QuipuUiApp` 实例化。
3. 确保所有测试通过。

## 基本原理
为测试用例注入一个简单的 Lambda 函数 `lambda n: "mock content"` 作为 `content_loader`，满足类型签名要求且不影响测试逻辑（因为这些测试主要关注图谱渲染和可达性计算，不涉及内容加载）。

## 标签
#comp/tests #scope/dx #fix

---

## Script

### Acts 1: 修复 UI 逻辑测试

为 `test_ui_logic.py` 中的 App 实例化添加 `content_loader` 参数。

~~~~~act
replace tests/test_ui_logic.py
~~~~~
~~~~~python
        node_c = QuipuNode("b", "c", datetime(2023,1,3), Path("f"), "plan")
        
        app = QuipuUiApp([node_a, node_b, node_c])
        
        # 我们可以通过 mock table 来验证，或者简单地运行 _populate_table 看是否报错
~~~~~
~~~~~python
        node_c = QuipuNode("b", "c", datetime(2023,1,3), Path("f"), "plan")
        
        app = QuipuUiApp([node_a, node_b, node_c], content_loader=lambda n: "mock")
        
        # 我们可以通过 mock table 来验证，或者简单地运行 _populate_table 看是否报错
~~~~~

~~~~~act
replace tests/test_ui_logic.py
~~~~~
~~~~~python
        node_c = QuipuNode("a", "c", datetime(2023,1,3), Path("f"), "plan") # Branch C is newer
        
        app = QuipuUiApp([node_a, node_b, node_c])
        
        # 验证排序: C (newest), B, A
~~~~~
~~~~~python
        node_c = QuipuNode("a", "c", datetime(2023,1,3), Path("f"), "plan") # Branch C is newer
        
        app = QuipuUiApp([node_a, node_b, node_c], content_loader=lambda n: "mock")
        
        # 验证排序: C (newest), B, A
~~~~~

~~~~~act
replace tests/test_ui_logic.py
~~~~~
~~~~~python
    def test_get_node_summary(self):
        """
        测试 TUI 是否正确使用预加载的 summary 字段，而不是动态解析。
        """
        app = QuipuUiApp([], None)

        # 案例 1: 节点带有预设的 summary
~~~~~
~~~~~python
    def test_get_node_summary(self):
        """
        测试 TUI 是否正确使用预加载的 summary 字段，而不是动态解析。
        """
        app = QuipuUiApp([], content_loader=lambda n: "mock", current_hash=None)

        # 案例 1: 节点带有预设的 summary
~~~~~

### Acts 2: 修复 UI 可达性测试

为 `test_ui_reachability.py` 中的 App 实例化添加 `content_loader` 参数。

~~~~~act
replace tests/test_ui_reachability.py
~~~~~
~~~~~python
        # Scenario 1: Focus on 'curr'
        # Reachable should be: curr, a, root (Ancestors) + (Descendants: None)
        # Unreachable: b
        app = QuipuUiApp([root, node_a, node_b, node_current], current_hash="curr")
        reachable = app.reachable_hashes
        
        assert "curr" in reachable
~~~~~
~~~~~python
        # Scenario 1: Focus on 'curr'
        # Reachable should be: curr, a, root (Ancestors) + (Descendants: None)
        # Unreachable: b
        app = QuipuUiApp([root, node_a, node_b, node_current], content_loader=lambda n: "mock", current_hash="curr")
        reachable = app.reachable_hashes
        
        assert "curr" in reachable
~~~~~

~~~~~act
replace tests/test_ui_reachability.py
~~~~~
~~~~~python
        # Scenario 2: Focus on 'root'
        # Reachable: root + all descendants (a, b, curr)
        app_root = QuipuUiApp([root, node_a, node_b, node_current], current_hash="root")
        reachable_root = app_root.reachable_hashes
        
        assert "curr" in reachable_root
~~~~~
~~~~~python
        # Scenario 2: Focus on 'root'
        # Reachable: root + all descendants (a, b, curr)
        app_root = QuipuUiApp([root, node_a, node_b, node_current], content_loader=lambda n: "mock", current_hash="root")
        reachable_root = app_root.reachable_hashes
        
        assert "curr" in reachable_root
~~~~~

~~~~~act
replace tests/test_ui_reachability.py
~~~~~
~~~~~python
        node_c = QuipuNode("root", "c", datetime(2023,1,3), Path("f"), "plan")
        
        nodes = [node_a, node_b, node_c]
        app = QuipuUiApp(nodes, current_hash="a")
        
        # 1. Default: Show all, but C is dim (logic handled in rendering string, hard to test here without inspecting Textual widgets deep state)
~~~~~
~~~~~python
        node_c = QuipuNode("root", "c", datetime(2023,1,3), Path("f"), "plan")
        
        nodes = [node_a, node_b, node_c]
        app = QuipuUiApp(nodes, content_loader=lambda n: "mock", current_hash="a")
        
        # 1. Default: Show all, but C is dim (logic handled in rendering string, hard to test here without inspecting Textual widgets deep state)
~~~~~
