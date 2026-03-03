import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score


def auto_select_k(Xs, max_k=8):
    inertias = []
    silhouettes = []
    K = range(2, max_k + 1)
    for k in K:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(Xs)
        inertias.append(km.inertia_)
        try:
            sil = silhouette_score(Xs, labels)
        except Exception:
            sil = np.nan
        silhouettes.append(sil)

    # Prefer silhouette (choose k with max silhouette), fall back to elbow heuristic
    if np.all(np.isnan(silhouettes)):
        # simple elbow: pick k where reduction in inertia levels off (max second derivative)
        diffs = np.diff(inertias)
        second_diffs = np.diff(diffs)
        if len(second_diffs) > 0:
            choice = 2 + int(np.argmax(-second_diffs))  # +2 because K starts at 2
        else:
            choice = 2
    else:
        choice = int(K[int(np.nanargmax(silhouettes))])

    return choice, list(K), inertias, silhouettes


def run_clustering(features_csv, longform_csv, out_csv="feature_clusters.csv", out_plot="feature_clusters.png", n_clusters=3, auto_k=False, max_k=8):
    # Load taxonomy
    tax = pd.read_csv(features_csv)

    # Load longform mapping (movie -> feature)
    # Read trigger so we count only positive triggers (feature present)
    df = pd.read_csv(longform_csv, usecols=["imdb_id", "feature_id", "trigger"])

    # Compute movie counts per feature (unique imdb_id where trigger>0)
    pos = df[df["trigger"] > 0]
    counts = pos.groupby("feature_id").imdb_id.nunique().reset_index()
    counts.columns = ["feature_id", "movie_count"]

    # Merge with taxonomy to get feature names
    merged = tax.merge(counts, how="left", left_on="feature_id", right_on="feature_id")
    merged["movie_count"] = merged["movie_count"].fillna(0).astype(int)

    # Prepare data for clustering
    X = merged[["movie_count"]].astype(float)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    # automatic k selection if requested
    if auto_k:
        best_k, K_range, inertias, silhouettes = auto_select_k(Xs, max_k=max_k)
        n_clusters = best_k
        # save diagnostic plots
        plt.figure(figsize=(8, 4))
        plt.plot(K_range, inertias, '-o')
        plt.xlabel('k')
        plt.ylabel('Inertia')
        plt.title('Elbow plot')
        plt.tight_layout()
        elbow_path = os.path.splitext(out_plot)[0] + '_elbow.png'
        plt.savefig(elbow_path)

        plt.figure(figsize=(8, 4))
        plt.plot(K_range, silhouettes, '-o')
        plt.xlabel('k')
        plt.ylabel('Silhouette score')
        plt.title('Silhouette scores')
        plt.tight_layout()
        sil_path = os.path.splitext(out_plot)[0] + '_silhouette.png'
        plt.savefig(sil_path)

    # KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(Xs)
    merged["cluster"] = labels

    # Save results
    merged.to_csv(out_csv, index=False)

    # Plot: distribution of movie_count colored by cluster (violin + strip)
    plt.figure(figsize=(10, 6))
    sns.violinplot(x="cluster", y="movie_count", data=merged, inner=None, color="lightgray")
    sns.stripplot(x="cluster", y="movie_count", data=merged, jitter=True, alpha=0.7)
    plt.yscale('log')
    plt.ylabel("movie_count (log scale)")
    plt.title(f"Feature clusters (k={n_clusters}) by movie count")
    plt.tight_layout()
    plt.savefig(out_plot)

    return merged


def main():
    parser = argparse.ArgumentParser(description="Cluster features by movie count")
    parser.add_argument("--features", default="feature_taxonomy.csv")
    parser.add_argument("--longform", default="feature_data_longform.csv")
    parser.add_argument("--out-csv", default="feature_clusters.csv")
    parser.add_argument("--out-plot", default="feature_clusters.png")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--auto-k", action="store_true", help="Automatically select k using silhouette/elbow")
    parser.add_argument("--max-k", type=int, default=8, help="Maximum k to try when using --auto-k")
    args = parser.parse_args()
    merged = run_clustering(args.features, args.longform, args.out_csv, args.out_plot, args.k, auto_k=args.auto_k, max_k=args.max_k)
    print(f"Saved clusters to {args.out_csv} and plot to {args.out_plot}")


if __name__ == "__main__":
    main()
