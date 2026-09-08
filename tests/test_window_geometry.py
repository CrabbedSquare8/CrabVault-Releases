from types import SimpleNamespace

import main


def _screen(x, y, width, height):
    frame = SimpleNamespace(X=x, Y=y, Width=width, Height=height)
    return SimpleNamespace(x=x, y=y, width=width, height=height, frame=frame)


def test_initial_window_keeps_margins_on_smaller_screen():
    geometry = main._initial_window_geometry(_screen(0, 0, 1280, 720))

    assert geometry == {"width": 1152, "height": 648, "x": 64, "y": 36}


def test_initial_window_is_capped_and_centered_on_large_screen():
    geometry = main._initial_window_geometry(_screen(100, 40, 1920, 1040))

    assert geometry == {"width": 1280, "height": 800, "x": 420, "y": 160}


def test_initial_window_never_exceeds_tiny_work_area():
    geometry = main._initial_window_geometry(_screen(-800, 0, 640, 480))

    assert geometry == {"width": 640, "height": 480, "x": -800, "y": 0}


def test_custom_titlebar_uses_pywebview_drag_region():
    html = (main.pathlib.Path(main.FRONTEND_DIR) / "index.html").read_text(encoding="utf-8")

    assert 'class="titlebar-title pywebview-drag-region"' in html
    assert 'class="titlebar-controls"' in html
