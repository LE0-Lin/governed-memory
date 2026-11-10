//! Pure ranking kernels. Authentication and persistent state stay in the Python ledger.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};

fn cosine(a: &[f64], b: &[f64]) -> Result<f64, &'static str> {
    if a.is_empty() || a.len() != b.len() || a.iter().chain(b).any(|x| !x.is_finite()) {
        return Err("vectors must be nonempty, finite and have matching dimensions");
    }
    let dot: f64 = a.iter().zip(b).map(|(x, y)| x * y).sum();
    let norm = (a.iter().map(|x| x * x).sum::<f64>() * b.iter().map(|x| x * x).sum::<f64>()).sqrt();
    let score = dot / norm.max(1e-12);
    if score.is_finite() {
        Ok(score)
    } else {
        Err("vector magnitude overflow")
    }
}

fn order(scores: &[f64], ids: &[String]) -> Vec<usize> {
    let mut indices: Vec<_> = (0..scores.len()).collect();
    indices.sort_by(|&a, &b| {
        scores[b]
            .total_cmp(&scores[a])
            .then_with(|| ids[a].cmp(&ids[b]))
    });
    indices
}

/// BM25Okapi defaults (k1=1.5, b=.75, epsilon=.25), cosine, then reciprocal rank fusion.
#[pyfunction]
fn hybrid_order(
    query: Vec<String>,
    corpus: Vec<Vec<String>>,
    query_vector: Vec<f64>,
    vectors: Vec<Vec<f64>>,
    ids: Vec<String>,
) -> PyResult<Vec<usize>> {
    let n = corpus.len();
    if vectors.len() != n || ids.len() != n || ids.iter().collect::<HashSet<_>>().len() != n {
        return Err(PyValueError::new_err(
            "documents, vectors and unique IDs must align",
        ));
    }
    if n == 0 {
        return Ok(vec![]);
    }
    if corpus.iter().any(Vec::is_empty) {
        return Err(PyValueError::new_err(
            "tokenized documents must not be empty",
        ));
    }
    let mut df: HashMap<&str, usize> = HashMap::new();
    let counts: Vec<HashMap<&str, usize>> = corpus
        .iter()
        .map(|tokens| {
            let mut counts = HashMap::new();
            for token in tokens {
                *counts.entry(token.as_str()).or_insert(0) += 1;
            }
            for token in counts.keys() {
                *df.entry(token).or_insert(0) += 1;
            }
            counts
        })
        .collect();
    let mut idf: HashMap<&str, f64> = df
        .iter()
        .map(|(&word, &freq)| {
            (
                word,
                ((n as f64 - freq as f64 + 0.5) / (freq as f64 + 0.5)).ln(),
            )
        })
        .collect();
    let floor = 0.25 * idf.values().sum::<f64>() / idf.len() as f64;
    for score in idf.values_mut() {
        if *score < 0.0 {
            *score = floor;
        }
    }
    let average_length = corpus.iter().map(Vec::len).sum::<usize>() as f64 / n as f64;
    let lexical: Vec<f64> = counts
        .iter()
        .enumerate()
        .map(|(i, counts)| {
            query
                .iter()
                .map(|word| {
                    let frequency = *counts.get(word.as_str()).unwrap_or(&0) as f64;
                    idf.get(word.as_str()).unwrap_or(&0.0) * frequency * 2.5
                        / (frequency
                            + 1.5 * (0.25 + 0.75 * corpus[i].len() as f64 / average_length))
                })
                .sum()
        })
        .collect();
    let semantic = vectors
        .iter()
        .map(|v| cosine(v, &query_vector))
        .collect::<Result<Vec<_>, _>>()
        .map_err(PyValueError::new_err)?;
    let mut fused = vec![0.0; n];
    for ranked in [order(&lexical, &ids), order(&semantic, &ids)] {
        for (rank, index) in ranked.into_iter().enumerate() {
            fused[index] += 1.0 / (61 + rank) as f64;
        }
    }
    Ok(order(&fused, &ids))
}

/// Select boundaries between adjacent sentence vectors, bounded by source token counts.
#[pyfunction]
fn semantic_spans(
    vectors: Vec<Vec<f64>>,
    token_counts: Vec<usize>,
    max_tokens: usize,
    min_tokens: usize,
    threshold: f64,
) -> PyResult<Vec<(usize, usize)>> {
    if vectors.len() != token_counts.len()
        || min_tokens == 0
        || min_tokens > max_tokens
        || !threshold.is_finite()
        || !(-1.0..=1.0).contains(&threshold)
        || token_counts.iter().any(|&n| n == 0 || n > max_tokens)
    {
        return Err(PyValueError::new_err(
            "invalid semantic segmentation limits",
        ));
    }
    for vector in &vectors {
        cosine(vector, vector).map_err(PyValueError::new_err)?;
    }
    let mut spans = vec![];
    let (mut start, mut used) = (0, 0);
    for i in 0..vectors.len() {
        let drift = i > start
            && used >= min_tokens
            && cosine(&vectors[i - 1], &vectors[i]).map_err(PyValueError::new_err)? < threshold;
        if i > start && (used + token_counts[i] > max_tokens || drift) {
            spans.push((start, i));
            start = i;
            used = 0;
        }
        used += token_counts[i];
    }
    if start < vectors.len() {
        spans.push((start, vectors.len()));
    }
    Ok(spans)
}

#[pymodule]
fn governed_memory_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(hybrid_order, m)?)?;
    m.add_function(wrap_pyfunction!(semantic_spans, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cosine_rejects_bad_vectors_and_handles_zero() {
        assert_eq!(cosine(&[0.0, 0.0], &[1.0, 0.0]), Ok(0.0));
        assert!(cosine(&[f64::NAN], &[1.0]).is_err());
        assert!(cosine(&[1.0], &[1.0, 2.0]).is_err());
    }

    #[test]
    fn semantic_drift_splits_similar_sentences_from_new_topic() {
        let spans = semantic_spans(
            vec![vec![1.0, 0.0], vec![0.9, 0.1], vec![0.0, 1.0]],
            vec![20, 20, 20],
            100,
            30,
            0.5,
        )
        .unwrap();
        assert_eq!(spans, vec![(0, 2), (2, 3)]);
    }
}
