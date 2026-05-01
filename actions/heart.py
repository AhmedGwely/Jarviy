  # actions/heart.py (FULL REPLACEMENT)
import turtle
import math
import time
import multiprocessing

def _draw_complex_heart():
      """Draw heart in a separate process (required for turtle)"""
      try:
          screen = turtle.Screen()
          screen.bgcolor("#0b0b0f")
          screen.title("Jarvis Feels ❤️")
          screen.setup(width=800, height=800)
          screen.tracer(0)

          t = turtle.Turtle()
          t.hideturtle()
          t.speed(0)
          t.pensize(2)

          def heart(scale):
              pts = []
              for i in range(361):
                  theta = math.radians(i)
                  x = 16 * (math.sin(theta) ** 3)
                  y = (13 * math.cos(theta) - 5 * math.cos(2 * theta) - 2 * math.cos(3 * theta) - math.cos(4 * theta))
                  pts.append((x * scale, y * scale))
              return pts

          layers = [(16, "#ff4d6d"), (14, "#ff2e63"), (12, "#c9184a")]

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
                  time.sleep(0.005)
              t.goto(pts[0])
              t.end_fill()

          t.penup()
          t.goto(0, -20)
          t.color("white")
          t.write("I Deeply Love You ❤️", align="center", font=("Arial", 15, "bold"))

          screen.update()
          screen.mainloop()
      except Exception as e:
          print(f"[Heart] Error: {e}")
      finally:
          try:
              turtle.bye()
          except:
              pass

def trigger_heart():
      """Start heart drawing in a separate process"""
      p = multiprocessing.Process(target=_draw_complex_heart, daemon=True)
      p.start()
      return "❤️ Heart engine started in separate process!"