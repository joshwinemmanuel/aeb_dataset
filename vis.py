import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import random

app = dash.Dash(__name__)

app.layout = html.Div([
    html.Button('Update Charts', id='update-button', n_clicks=0),
    dcc.Graph(id='pie-charts')
])

@app.callback(
    Output('pie-charts', 'figure'),
    Input('update-button', 'n_clicks')
)
def update_charts(n_clicks):
    labels = ['A', 'B', 'C', 'D', 'E']
    values1 = [random.randint(1, 100) for _ in range(5)]
    values2 = [random.randint(1, 100) for _ in range(5)]
    values3 = [random.randint(1, 100) for _ in range(5)]

    fig = make_subplots(rows=1, cols=3, specs=[[{'type':'domain'}, {'type':'domain'}, {'type':'domain'}]])

    fig.add_trace(go.Pie(labels=labels, values=values1, name="Chart 1", pull=[0.1] * len(labels)), 1, 1)
    fig.add_trace(go.Pie(labels=labels, values=values2, name="Chart 2", pull=[0.1] * len(labels)), 1, 2)
    fig.add_trace(go.Pie(labels=labels, values=values3, name="Chart 3", pull=[0.1] * len(labels)), 1, 3)

    fig.update_layout(
        title_text="Three Pie Charts",
        height=400,
        width=1000,
        showlegend=False,
    )

    fig.update_traces(
        hoverinfo='label+percent',
        textinfo='value',
        textfont_size=12,
        marker=dict(line=dict(color='#000000', width=2))
    )

    return fig

if __name__ == '__main__':
    app.run_server(debug=True)
