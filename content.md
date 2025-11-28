Of course. We have completed a significant set of improvements to the TUI, addressing performance, stability, and usability. It is now time to consolidate this work into a single, comprehensive commit.

I will generate the final `[COMMIT]` plan.

## [COMMIT] feat(cli/tui): 增强 TUI 性能并添加渲染控制

### 用户需求
The Quipu TUI needed significant enhancements to address performance issues during scrolling, improve stability, and give users more control over the content rendering. The key requirements were to make scrolling responsive, prevent crashes from malformed content, add a plain-text viewing mode, and ensure content consistency between different views.

### 评论
This is a major user experience overhaul for the Quipu TUI. By implementing a debounced rendering strategy with an instant plain-text preview, we've made the application feel significantly more responsive. Adding user-configurable rendering modes (`--raw` flag and a hotkey) and fixing critical stability and layout bugs (markup parsing, missing scrollbars) transforms the TUI from a proof-of-concept into a robust and genuinely useful tool for exploring Quipu history.

### 目标
1.  **Performance**: The TUI is now highly responsive during scrolling, showing an instant plain-text preview of content.
2.  **Stability**: Crashes related to markup parsing have been eliminated by correctly configuring the preview widget.
3.  **Usability**: A missing scrollbar in the raw text view has been fixed.
4.  **Customization**: Users can now start the TUI in a performance-focused raw text mode via a `--raw` flag and can toggle Markdown rendering on/off at runtime with the `m` key.
5.  **Consistency**: Both raw and Markdown views now display the exact same content, including public and private data.
6.  **Git History**: All these related changes are now ready to be committed as a single, logical feature enhancement.

### 基本原理
The solution combines several techniques:
-   **Debounced Rendering**: A state machine (`LOADING` -> `SHOWING_CONTENT`) uses a `Timer` to delay expensive Markdown rendering until the user stops scrolling.
-   **Instant Preview**: During the `LOADING` state, a `Static` widget configured with `markup=False` displays the node's full content as plain text, providing immediate feedback.
-   **Robust Layout**: CSS properties (`overflow-y: scroll` on the container and `height: auto` on the content widget) are correctly used to ensure scrolling is available in all modes.
-   **Stateful Configuration**: A `self.markdown_enabled` flag, controlled by a command-line option and a hotkey, dictates which final view (Markdown or Static) is displayed.

### 标签
#intent/build #intent/refine #intent/fix #flow/ready #priority/high #comp/cli #concept/ui #scope/ux #ai/instruct #task/domain/ui #task/object/tui-performance #task/action/optimization #task/state/end #task/status/completed

---

### Script

#### Acts 1: Stage and Commit All TUI Enhancements

We will now add all the modified files to the Git staging area and create a single, well-documented commit that captures the full scope of this feature.

~~~~~act
git_add
packages/quipu-cli/src/quipu/cli/commands/ui.py
packages/quipu-cli/src/quipu/cli/tui.py
packages/quipu-cli/src/quipu/cli/tui.css
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~text
feat(cli/tui): enhance TUI performance and add rendering controls

Implements a comprehensive overhaul of the TUI to improve performance, stability, and user control over content rendering.

Key Improvements:
-   **Performance:** Introduces a debounced rendering mechanism. While scrolling, a fast, plain-text preview is shown instantly. Full Markdown rendering is deferred until scrolling stops, making the UI feel significantly more responsive.
-   **Stability:**
    -   Fixes critical crashes caused by the `Static` widget attempting to parse markup in raw node content. The preview widget is now correctly configured with `markup=False`.
    -   Resolves layout issues where the raw text view was missing a scrollbar by applying correct CSS (`overflow-y: scroll`).
-   **Features & UX:**
    -   Adds a `--raw` command-line flag to the `ui` command, allowing users to start in a high-performance, plain-text-only mode.
    -   Introduces an `m` keybinding to toggle Markdown rendering on and off at runtime.
    -   Ensures content consistency by making both raw and Markdown views display the same complete data bundle (public and private content).
    -   The footer now dynamically displays the current rendering mode.
~~~~~

### 下一步建议
The TUI is now in a much more stable and feature-complete state. Future work could focus on:
-   **Search/Filter**: Adding a command palette or a filter bar to quickly search for nodes within the TUI.
-   **Branch Visualization**: Improving the graph rendering to better handle complex branching and merging scenarios.
-   **Actions**: Adding more actions that can be triggered from within the TUI, such as creating a `save` point or deleting a node.
