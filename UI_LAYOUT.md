# Enaml Layout Notes

## HGroup: align_widths and fixed-size buttons

HGroup defaults to `align_widths = True`, which forces all children to equal width.
This breaks when you mix stretchy Fields with fixed-size buttons (e.g. a 30px "X" remove button).

**Pattern** (from instance_list.enaml):
```
HGroup:
    align_widths = False
    Field:
        hug_width = 'ignore'    # stretches to fill
    PushButton:
        text = "X"
        minimum_size = (30, 0)
        maximum_size = (30, 16777215)
```

Without `align_widths = False`, the equal-width constraint fights with `minimum_size`/`maximum_size`
on the button and the layout breaks.

## Disabling UI during async operations

Setting `enabled = False` on a container (e.g. Splitter) disables all children recursively (Qt propagation).
Use a single binding on the outermost container rather than per-button `enabled` checks.

**Pattern** (from main_window.enaml):
```
Splitter: splitter:
    enabled << not app_model.busy
    SplitItem:
        ...  # all children disabled when busy
```

Do **not** add `enabled << not app_model.busy` to individual buttons inside the splitter — the parent
binding handles it. Only add per-widget `enabled` bindings for things outside the disabled container
(e.g. ToolBar actions).

## Status bar: fixed height to prevent splitter resize

Toggling `visible` on a child widget (e.g. ProgressBar) causes the parent container to recalculate
its preferred size, which can make a `vbox` constraint engine resize the splitter above it.

**Fix**: pin the status bar height with `minimum_size` / `maximum_size` and set `align_widths = False`:
```
HGroup: status_bar:
    align_widths = False
    padding = 0
    trailing_spacer = None
    minimum_size = (0, 28)
    maximum_size = (16777215, 28)
    ProgressBar:
        visible << app_model.busy
        ...
    Label:
        text << app_model.status_message
```

## Atom objects and Qt signals

Atom objects do not support `__weakref__`, so `signal.connect(atom_obj.method)` raises
`TypeError: cannot create weak reference to 'AppModel' object`.

**Fix**: wrap in a lambda:
```python
timer.timeout.connect(lambda: app_model.poll_status())
```
