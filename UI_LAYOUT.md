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
