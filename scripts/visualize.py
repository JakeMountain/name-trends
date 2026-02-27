#!/usr/bin/env python3
"""
visualize.py

Generates interactive Plotly visualizations from analysis results.

Outputs (all standalone HTML, no server needed):
    viz/lag_explorer.html       — per-name gazette freq vs baby freq with lag slider
    viz/hot_names.html          — names trending in gazette but not yet in babies
    viz/mtf_vs_ftm.html         — side-by-side lag distributions
    viz/dose_response.html      — threshold vs mean lag interactive curve

Usage:
    python scripts/visualize.py \
        --results-dir data/processed/ \
        --name-changes data/raw/ontario_name_changes.csv \
        --baby-names-female data/raw/ontario_baby_names_female.csv \
        --baby-names-male data/raw/ontario_baby_names_male.csv \
        --output-dir viz/
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
except ImportError:
    print("pip install plotly")
    sys.exit(1)


# ── data helpers ──────────────────────────────────────────────────────────────

def load_name_changes(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['year'] = pd.to_datetime(df['gazette_date']).dt.year
    df['new_first_name'] = df['new_first_name'].str.upper().str.strip()
    df['old_first_name'] = df['old_first_name'].str.upper().str.strip()
    df = df[df['old_first_name'] != df['new_first_name']]
    return df


def load_baby_names(female_path: str, male_path: str) -> pd.DataFrame:
    def _load(path, sex):
        df = pd.read_csv(path)
        df.columns = df.columns.str.lower().str.strip()
        rename_map = {}
        for col in df.columns:
            if any(s in col for s in ['name', 'nom', 'nombre']):
                rename_map[col] = 'first_name'
            elif any(s in col for s in ['frequency', 'count', 'freq']):
                rename_map[col] = 'count'
            elif any(s in col for s in ['year', 'année', 'anno']):
                rename_map[col] = 'year'
        df = df.rename(columns=rename_map)
        df['first_name'] = df['first_name'].str.upper().str.strip()
        df['sex'] = sex
        return df

    return pd.concat([_load(female_path, 'F'), _load(male_path, 'M')], ignore_index=True)


def name_freq_by_year(df: pd.DataFrame, name_col: str, count_col: str | None = None,
                      year_col: str = 'year') -> pd.DataFrame:
    if count_col and count_col in df.columns:
        yearly = df.groupby([year_col, name_col])[count_col].sum().reset_index()
        yearly.columns = ['year', 'name', 'count']
    else:
        yearly = df.groupby([year_col, name_col]).size().reset_index(name='count')
        yearly = yearly.rename(columns={name_col: 'name'})
    totals = yearly.groupby('year')['count'].transform('sum')
    yearly['freq'] = yearly['count'] / totals
    return yearly


# ── viz 1: lag explorer ───────────────────────────────────────────────────────

_LAG_EXPLORER_JS = r"""
(function() {
    var gd = document.querySelector('.plotly-graph-div');
    if (!gd) return;

    // ── search box ──────────────────────────────────────────────────────────
    var wrapper = gd.parentElement;
    var searchBox = document.createElement('input');
    searchBox.type = 'text';
    searchBox.placeholder = 'Search name (e.g. AURORA) ...';
    searchBox.style.cssText = (
        'width:280px;padding:6px 10px;font-size:14px;border:1px solid #ccc;' +
        'border-radius:4px;margin:8px 0 4px 60px;display:block;'
    );
    wrapper.insertBefore(searchBox, gd);

    var hint = document.createElement('div');
    hint.textContent = 'Click a dot to see its time series below.  Double-click to reset.';
    hint.style.cssText = 'color:#888;font-size:12px;margin:0 0 4px 60px;';
    wrapper.insertBefore(hint, gd);

    function applySearch(q) {
        q = q.trim().toUpperCase();
        var scatter = gd.data[0];
        var names = scatter.customdata.map(function(d) { return d[0]; });
        var opacity = names.map(function(n) {
            if (!q) return 1.0;
            return n.indexOf(q) !== -1 ? 1.0 : 0.08;
        });
        Plotly.restyle(gd, {'marker.opacity': [opacity]}, [0]);
    }

    searchBox.addEventListener('input', function() { applySearch(this.value); });

    // ── click -> time series ────────────────────────────────────────────────
    gd.on('plotly_click', function(data) {
        var pt = data.points[0];
        if (pt.curveNumber !== 0) return;
        var cd  = pt.customdata;
        // customdata layout: [name, lag, nc_years[], nc_freqs[], baby_years[], baby_freqs[]]
        var name  = cd[0];
        var lag   = cd[1];
        var ncYrs = cd[2];
        var ncFqs = cd[3];
        var byYrs = cd[4];
        var byFqs = cd[5];

        var lagStr = lag > 0 ? '+' + lag : '' + lag;

        Plotly.restyle(gd, {
            x: [ncYrs, byYrs],
            y: [ncFqs, byFqs],
            name: ['Gazette (name changes)', 'Baby names']
        }, [1, 2]);

        Plotly.relayout(gd, {
            'annotations[0]': {
                text: '<b>' + name + '</b>  |  optimal lag = ' + lagStr + ' yr',
                x: 0.5, xref: 'paper', y: 0.35, yref: 'paper',
                showarrow: false, font: {size: 13}, xanchor: 'center'
            }
        });
    });

    gd.on('plotly_doubleclick', function() {
        Plotly.restyle(gd, {x: [[], []], y: [[], []]}, [1, 2]);
        Plotly.relayout(gd, {'annotations[0]': {text: ''}});
    });
})();
"""


def make_lag_explorer(corr_csv: Path, nc_df: pd.DataFrame, baby_df: pd.DataFrame,
                      output_path: Path):
    """
    Interactive scatter with search box and time-series click detail.
    Standalone HTML — no server needed.
    """
    if not corr_csv.exists():
        print(f"  Skipping lag explorer — {corr_csv} not found.")
        return

    corr = pd.read_csv(corr_csv)
    if corr.empty:
        print("  No names for lag explorer.")
        return

    corr = corr.copy()
    corr['_sig'] = corr['best_pvalue'] < 0.05

    nc_yearly = name_freq_by_year(nc_df, 'new_first_name')
    baby_yearly = name_freq_by_year(baby_df, 'first_name', 'count')

    # Build customdata: [name, lag, nc_years[], nc_freqs[], baby_years[], baby_freqs[], sig]
    custom = []
    for _, row in corr.iterrows():
        name = row['name']
        nc_s = nc_yearly[nc_yearly['name'] == name].sort_values('year')
        by_s = baby_yearly[baby_yearly['name'] == name].sort_values('year')
        custom.append([
            name,
            int(row['best_lag']),
            nc_s['year'].tolist(),
            [round(v, 6) for v in nc_s['freq'].tolist()],
            by_s['year'].tolist(),
            [round(v, 6) for v in by_s['freq'].tolist()],
            round(float(row['best_pvalue']), 4),
        ])

    # Marker visuals: significant = larger/opaque, non-sig = smaller/faded
    sizes = [10 if row['_sig'] else 6 for _, row in corr.iterrows()]
    opacities = [0.9 if row['_sig'] else 0.3 for _, row in corr.iterrows()]

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.58, 0.42],
        subplot_titles=['', ''],
        vertical_spacing=0.14,
    )

    # Row 1: scatter — all names, sig ones larger/brighter
    fig.add_trace(go.Scatter(
        x=corr['best_lag'],
        y=corr['best_correlation'],
        mode='markers',
        marker=dict(
            size=sizes,
            color=corr['best_lag'],
            colorscale='RdBu',
            cmid=0,
            colorbar=dict(title='Lag (y)', x=1.02, len=0.55, y=0.75),
            opacity=opacities,
        ),
        customdata=custom,
        text=corr['name'],
        hovertemplate='<b>%{text}</b><br>lag=%{x}y  r=%{y:.3f}  p=%{customdata[6]:.4f}<extra></extra>',
        showlegend=False,
    ), row=1, col=1)
    fig.add_vline(x=0, line_dash='dash', line_color='gray', row=1, col=1)

    # Row 2: blank time-series traces (populated by JS on click)
    fig.add_trace(go.Scatter(
        x=[], y=[], name='Gazette', mode='lines+markers',
        line=dict(color='#e45756', width=2), marker=dict(size=5),
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=[], y=[], name='Baby names', mode='lines+markers',
        line=dict(color='#4c78a8', width=2, dash='dot'), marker=dict(size=5),
        yaxis='y4',
    ), row=2, col=1)

    fig.update_layout(
        title=dict(
            text='Lag Explorer — Name Changes vs Baby Names<br>'
                 '<sup>Positive lag = gazette leads baby trend. Large dots = p&lt;0.05. Search above, click a dot.</sup>',
            x=0.5,
        ),
        height=820,
        xaxis=dict(title='Optimal lag (years)'),
        yaxis=dict(title='Pearson r'),
        xaxis2=dict(title='Year'),
        yaxis3=dict(title='Gazette freq', side='left'),
        yaxis4=dict(title='Baby freq', overlaying='y3', side='right'),
        legend=dict(x=1.05, y=0.3),
    )

    fig.write_html(output_path, include_plotlyjs='cdn', post_script=_LAG_EXPLORER_JS)
    print(f"  Lag explorer -> {output_path}")


# ── viz 2: hot names dashboard ────────────────────────────────────────────────

def make_hot_names(nc_df: pd.DataFrame, baby_df: pd.DataFrame,
                   output_path: Path, recent_years: int = 5, top_n: int = 30):
    """Names surging in gazette recently but not yet reflected in baby names."""
    max_year = nc_df['year'].max()
    recent_nc = nc_df[nc_df['year'] >= max_year - recent_years]
    prior_nc = nc_df[nc_df['year'] < max_year - recent_years]

    nc_recent_freq = (recent_nc.groupby('new_first_name').size() /
                      len(recent_nc)).rename('nc_recent')
    nc_prior_freq = (prior_nc.groupby('new_first_name').size() /
                     max(len(prior_nc), 1)).rename('nc_prior')

    baby_recent = baby_df[baby_df['year'] >= max_year - recent_years]
    baby_freq = (baby_recent.groupby('first_name')['count'].sum() /
                 baby_recent['count'].sum()).rename('baby_freq')

    hot = (nc_recent_freq
           .to_frame()
           .join(nc_prior_freq, how='left')
           .join(baby_freq, how='left')
           .fillna(0))
    hot['nc_surge'] = hot['nc_recent'] - hot['nc_prior']
    # High gazette presence, low baby presence = "ahead of the curve"
    hot['hot_score'] = hot['nc_recent'] / (hot['baby_freq'] + 1e-7)
    hot = hot.nlargest(top_n, 'hot_score').reset_index()
    hot.columns = ['name'] + list(hot.columns[1:])

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=['Hot Score (gazette surge / baby freq)',
                                        'Recent gazette frequency'])
    fig.add_trace(
        go.Bar(x=hot['hot_score'], y=hot['name'], orientation='h',
               name='Hot score', marker_color='steelblue'),
        row=1, col=1
    )
    fig.add_trace(
        go.Bar(x=hot['nc_recent'], y=hot['name'], orientation='h',
               name='Gazette freq', marker_color='coral'),
        row=1, col=2
    )
    fig.update_layout(
        title=f'Hot Names: Surging in Gazette ({max_year-recent_years}–{max_year}) '
              f'but Not Yet in Baby Names<br>'
              f'<sup>These may become popular baby names in 5-10 years</sup>',
        height=700, showlegend=False,
    )
    fig.update_yaxes(autorange='reversed')
    fig.write_html(output_path, include_plotlyjs='cdn')
    print(f"  Hot names -> {output_path}")


# ── viz 3: MTF vs FTM lag comparison ──────────────────────────────────────────

def make_mtf_vs_ftm(results_dir: Path, output_path: Path):
    """Side-by-side lag distribution histograms for MTF vs FTM."""
    mtf_path = results_dir / 'correlation_results_mtf.csv'
    ftm_path = results_dir / 'correlation_results_ftm.csv'

    if not mtf_path.exists() or not ftm_path.exists():
        print(f"  Skipping MTF vs FTM — need both correlation_results_mtf.csv and _ftm.csv")
        return

    mtf = pd.read_csv(mtf_path)
    ftm = pd.read_csv(ftm_path)

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=[
                            f'MTF (n={len(mtf)}, mean lag={mtf["best_lag"].mean():.1f}y)',
                            f'FTM (n={len(ftm)}, mean lag={ftm["best_lag"].mean():.1f}y)',
                        ])
    bins = list(range(-11, 12))
    fig.add_trace(go.Histogram(x=mtf['best_lag'], xbins=dict(start=-11, end=11, size=1),
                               name='MTF', marker_color='salmon'), row=1, col=1)
    fig.add_trace(go.Histogram(x=ftm['best_lag'], xbins=dict(start=-11, end=11, size=1),
                               name='FTM', marker_color='cornflowerblue'), row=1, col=2)

    for col in [1, 2]:
        fig.add_vline(x=0, line_dash='dash', line_color='gray', row=1, col=col)

    fig.update_layout(
        title='MTF vs FTM: Optimal Lag Distribution<br>'
              '<sup>Positive = name change leads baby trend. '
              'Do MTF and FTM show different lead times?</sup>',
        height=500, showlegend=False,
        xaxis_title='Optimal lag (years)', xaxis2_title='Optimal lag (years)',
    )
    fig.write_html(output_path, include_plotlyjs='cdn')
    print(f"  MTF vs FTM -> {output_path}")


# ── viz 4: dose-response interactive ──────────────────────────────────────────

def make_dose_response(results_dir: Path, output_path: Path):
    """Interactive dose-response: threshold vs mean lag, coloured by N significant."""
    # Collect data from correlation_results_thresh_*.csv files
    rows = []
    for p in sorted(results_dir.glob('correlation_results_thresh_*.csv')):
        thresh_str = p.stem.replace('correlation_results_thresh_', '')
        try:
            thresh = float(thresh_str)
        except ValueError:
            continue
        df = pd.read_csv(p)
        sig = df[df['best_pvalue'] < 0.05]
        rows.append({
            'threshold': thresh,
            'mean_lag': sig['best_lag'].mean() if len(sig) > 0 else None,
            'median_lag': sig['best_lag'].median() if len(sig) > 0 else None,
            'n_sig': len(sig),
            'n_total': len(df),
        })

    if not rows:
        print(f"  Skipping dose-response — no correlation_results_thresh_*.csv files found.")
        return

    df = pd.DataFrame(rows).dropna(subset=['mean_lag'])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df['threshold'], y=df['mean_lag'],
                             mode='lines+markers', name='Mean lag (p<0.05)',
                             line=dict(color='steelblue', width=3),
                             marker=dict(size=10)),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df['threshold'], y=df['median_lag'],
                             mode='lines+markers', name='Median lag (p<0.05)',
                             line=dict(color='steelblue', width=2, dash='dash'),
                             marker=dict(size=8)),
                  secondary_y=False)
    fig.add_trace(go.Bar(x=df['threshold'], y=df['n_sig'],
                         name='N significant names', opacity=0.3,
                         marker_color='orange'),
                  secondary_y=True)
    fig.add_hline(y=0, line_dash='dash', line_color='gray')
    fig.update_layout(
        title='Dose-Response: Gender Delta Threshold vs Mean Optimal Lag<br>'
              '<sup>If slope > 0: stronger gender shift -> longer lead time (supports hypothesis)</sup>',
        xaxis_title='|Gender delta| threshold',
        height=500,
    )
    fig.update_yaxes(title_text='Mean/median lag (years)', secondary_y=False)
    fig.update_yaxes(title_text='N significant names', secondary_y=True)
    fig.write_html(output_path, include_plotlyjs='cdn')
    print(f"  Dose-response -> {output_path}")


# ── viz 5: pre/post 2006 comparison ───────────────────────────────────────────

def make_pre_post_2006(results_dir: Path, output_path: Path):
    """Overlay lag distributions pre vs post 2006 (trans opt-out natural experiment)."""
    pre_path = results_dir / 'correlation_results_pre2006.csv'
    post_path = results_dir / 'correlation_results_post2006.csv'

    if not pre_path.exists() or not post_path.exists():
        print(f"  Skipping pre/post-2006 — need both files.")
        return

    pre = pd.read_csv(pre_path)
    post = pd.read_csv(post_path)

    pre_sig = pre[pre['best_pvalue'] < 0.05]
    post_sig = post[post['best_pvalue'] < 0.05]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=pre_sig['best_lag'], name=f'Pre-2006 (mean={pre_sig["best_lag"].mean():.1f}y)',
        xbins=dict(start=-11, end=11, size=1),
        opacity=0.6, marker_color='steelblue',
    ))
    fig.add_trace(go.Histogram(
        x=post_sig['best_lag'], name=f'Post-2006 (mean={post_sig["best_lag"].mean():.1f}y)',
        xbins=dict(start=-11, end=11, size=1),
        opacity=0.6, marker_color='coral',
    ))
    fig.add_vline(x=0, line_dash='dash', line_color='gray')
    fig.update_layout(
        barmode='overlay',
        title='Pre vs Post-2006 Lag Distribution (Natural Experiment)<br>'
              '<sup>Post-2006 trans people can opt out of Gazette — '
              'if signal weakens, it is trans-specific</sup>',
        xaxis_title='Optimal lag (years)',
        yaxis_title='Number of names',
        height=500,
    )
    fig.write_html(output_path, include_plotlyjs='cdn')
    print(f"  Pre/post-2006 -> {output_path}")


# ── viz 6: curve score dashboard ──────────────────────────────────────────────

def make_curve_score_viz(results_dir: Path, output_path: Path):
    """
    Three-panel interactive dashboard for the per-record curve score analysis.

    Panel 1: Violin plot — curve_score distribution for MTF, FTM, and non-trans
    Panel 2: Mean curve_score by year (2000-2018) with trend lines per group
    Panel 3: Scatter of curve_score vs gender_delta, coloured by 5-year chunk
    """
    csv_path = results_dir / 'curve_scores.csv'
    if not csv_path.exists():
        print(f"  Skipping curve score viz — {csv_path} not found.")
        return

    df = pd.read_csv(csv_path).dropna(subset=['curve_score'])
    df['chunk'] = pd.cut(df['year'], bins=[1999,2004,2009,2014,2018],
                         labels=['2000-04','2005-09','2010-14','2015-18'])

    # Group labels
    mtf   = df[df['gender_delta'] >= 0.7]
    ftm   = df[df['gender_delta'] <= -0.7]
    trans = df[df['gender_delta'].abs() >= 0.7]
    non_t = df[df['gender_delta'].abs() < 0.1]

    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.30, 0.38, 0.32],
        subplot_titles=[
            'Distribution of curve scores by group  (positive = ahead of trend)',
            'Mean curve score over time — are trans people becoming more trend-setting?',
            'Curve score vs gender delta  (colour = era)',
        ],
        vertical_spacing=0.10,
    )

    # ── Panel 1: violin ──
    group_data = [
        ('MTF (d≥+0.7)',     mtf,   '#e45756'),
        ('FTM (d≤−0.7)',     ftm,   '#4c78a8'),
        ('Non-trans |d|<0.1',non_t, '#72b7b2'),
    ]
    for name, grp, color in group_data:
        fig.add_trace(go.Violin(
            y=grp['curve_score'], name=name,
            box_visible=True, meanline_visible=True,
            line_color=color, fillcolor=color, opacity=0.6,
            hovertemplate=f'<b>{name}</b><br>score=%{{y:.3f}}<extra></extra>',
        ), row=1, col=1)
    fig.add_hline(y=0, line_dash='dash', line_color='gray', row=1, col=1)

    # ── Panel 2: mean by year, with OLS trend lines ──
    from scipy import stats as _stats
    year_groups = [
        ('All trans',  trans,  '#555555'),
        ('MTF',        mtf,    '#e45756'),
        ('FTM',        ftm,    '#4c78a8'),
    ]
    for label, grp, color in year_groups:
        yearly = grp.groupby('year')['curve_score'].mean().reset_index()
        fig.add_trace(go.Scatter(
            x=yearly['year'], y=yearly['curve_score'],
            mode='lines+markers', name=label,
            line=dict(color=color, width=2), marker=dict(size=6),
            hovertemplate='%{x}  mean=%{y:.3f}<extra>' + label + '</extra>',
        ), row=2, col=1)
        # OLS trend line
        if len(yearly) >= 4:
            m, b, *_ = _stats.linregress(yearly['year'], yearly['curve_score'])
            x0, x1 = yearly['year'].min(), yearly['year'].max()
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[m*x0+b, m*x1+b],
                mode='lines', name=f'{label} trend',
                line=dict(color=color, dash='dot', width=1.5),
                showlegend=False,
                hovertemplate=f'{label} trend  slope={m:+.4f}/yr<extra></extra>',
            ), row=2, col=1)
    fig.add_hline(y=0, line_dash='dash', line_color='lightgray', row=2, col=1)

    # ── Panel 3: scatter curve_score vs gender_delta, coloured by chunk ──
    chunk_colors = {'2000-04':'#636EFA', '2005-09':'#EF553B',
                    '2010-14':'#00CC96', '2015-18':'#AB63FA'}
    for chunk, cdf in df.groupby('chunk', observed=True):
        fig.add_trace(go.Scatter(
            x=cdf['gender_delta'], y=cdf['curve_score'],
            mode='markers',
            marker=dict(size=3, color=chunk_colors.get(str(chunk), '#888'),
                        opacity=0.4),
            name=str(chunk),
            text=cdf['new_first_name'],
            hovertemplate='<b>%{text}</b><br>delta=%{x:.2f}  score=%{y:.3f}<extra></extra>',
        ), row=3, col=1)
    fig.add_hline(y=0, line_dash='dash', line_color='gray', row=3, col=1)
    fig.add_vline(x=0.7,  line_dash='dot', line_color='lightgray', row=3, col=1)
    fig.add_vline(x=-0.7, line_dash='dot', line_color='lightgray', row=3, col=1)

    # ── layout ──
    n_trans = len(trans)
    n_mtf, n_ftm = len(mtf), len(ftm)
    fig.update_layout(
        title=dict(
            text=(f'Curve Score Dashboard — "Ahead or Behind the Trend?"<br>'
                  f'<sup>Per-record score: +1=name was rising at time of change, '
                  f'-1=name was declining.  '
                  f'Trans n={n_trans:,} (MTF={n_mtf:,}, FTM={n_ftm:,}), '
                  f'window=±5y, records 2000-2018</sup>'),
            x=0.5,
        ),
        height=1100,
        yaxis=dict(title='Curve score', zeroline=False),
        yaxis2=dict(title='Mean curve score'),
        xaxis2=dict(title='Year'),
        yaxis3=dict(title='Curve score'),
        xaxis3=dict(title='Gender delta (−1=FTM, +1=MTF)'),
        legend=dict(x=1.02, y=0.95),
    )
    fig.write_html(output_path, include_plotlyjs='cdn')
    print(f"  Curve score viz -> {output_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Generate interactive Plotly visualizations')
    parser.add_argument('--results-dir', '-r', default='data/processed')
    parser.add_argument('--name-changes', '-n', required=True)
    parser.add_argument('--baby-names-female', '-f', required=True)
    parser.add_argument('--baby-names-male', '-m', required=True)
    parser.add_argument('--output-dir', '-o', default='viz')
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    print("Loading data...")
    nc_df = load_name_changes(args.name_changes)
    baby_df = load_baby_names(args.baby_names_female, args.baby_names_male)
    print(f"  {len(nc_df):,} name changes, {len(baby_df):,} baby name records")

    print("\nGenerating visualizations...")

    make_lag_explorer(
        results_dir / 'correlation_results_likely_trans.csv',
        nc_df, baby_df,
        output_dir / 'lag_explorer.html',
    )

    make_hot_names(nc_df, baby_df, output_dir / 'hot_names.html')

    make_mtf_vs_ftm(results_dir, output_dir / 'mtf_vs_ftm.html')

    make_dose_response(results_dir, output_dir / 'dose_response.html')

    make_pre_post_2006(results_dir, output_dir / 'pre_post_2006.html')

    make_curve_score_viz(results_dir, output_dir / 'curve_scores.html')

    print(f"\nAll visualizations written to {output_dir}/")
    print("Open any .html file in a browser — no server required.")


if __name__ == '__main__':
    main()
