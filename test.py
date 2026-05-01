# actions/heart.py

import turtle
import math
import time
import threading


def _draw_complex_heart():
    """Slow cinematic filled heart animation"""

    try:
        # -----------------------------
        # SCREEN SETUP
        # -----------------------------
        screen = turtle.Screen()
        screen.bgcolor("#0b0b0f")
        screen.title("Jarvis Feels ❤️")
        screen.setup(width=800, height=800)
        screen.tracer(0)

        screen.colormode(255)

        # -----------------------------
        # TURTLE SETUP
        # -----------------------------
        t = turtle.Turtle()
        t.hideturtle()
        t.speed(0)
        t.pensize(2)

        # -----------------------------
        # HEART FUNCTION
        # -----------------------------
        def heart(scale):
            pts = []
            for i in range(361):
                theta = math.radians(i)

                x = 16 * (math.sin(theta) ** 3)
                y = (
                    13 * math.cos(theta)
                    - 5 * math.cos(2 * theta)
                    - 2 * math.cos(3 * theta)
                    - math.cos(4 * theta)
                )

                pts.append((x * scale, y * scale))
            return pts

        # -----------------------------
        # LAYERS (FILL EFFECT)
        # -----------------------------
        layers = [
            (16, "#ff4d6d"),
            (14, "#ff2e63"),
            (12, "#c9184a"),
        ]

        # -----------------------------
        # SLOW DRAW SETTINGS
        # -----------------------------
        delay = 0.005

        for scale, color in layers:
            pts = heart(scale)

            t.penup()
            t.goto(pts[0])
            t.pendown()

            t.fillcolor(color)
            t.pencolor(color)

            t.begin_fill()

            for x, y in pts:
                t.goto(x, y)

                screen.update()
                time.sleep(delay)

            t.goto(pts[0])
            t.end_fill()

        # -----------------------------
        # TEXT
        # -----------------------------
        t.penup()
        t.goto(0, -20)
        t.color("white")
        t.write("I Deeply Love You ❤️", align="center", font=("Arial", 22, "bold"))

        screen.update()
        screen.mainloop()

    except Exception as e:
        print(f"[Heart] Error: {e}")


# -----------------------------
# THREAD WRAPPER (FIXED)
# -----------------------------
def trigger_heart():
    """Run heart in a safe thread"""

    def runner():
        _draw_complex_heart()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()

    return "❤️ Slow heart engine started in thread!"


# -----------------------------
# RUN DIRECTLY
# -----------------------------
if __name__ == "__main__":
    print(trigger_heart())

    # keep main alive so thread doesn't instantly die
    while True:
        time.sleep(1)