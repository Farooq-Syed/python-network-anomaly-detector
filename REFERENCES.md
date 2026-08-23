# References

This file collects the key external references for the network anomaly detector so
the README, paper draft, and application materials can cite them consistently.

## Benchmarks and dataset pages

1. Nour Moustafa and Jill Slay. *UNSW-NB15: a comprehensive data set for network
   intrusion detection systems (UNSW-NB15 network data set).* MilCIS 2015.
   Official dataset page: <https://research.unsw.edu.au/projects/unsw-nb15-dataset>

2. Iman Sharafaldin, Arash Habibi Lashkari, and Ali A. Ghorbani.
   *Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic
   Characterization.* ICISSP 2018.
   Official CIC-IDS2017 page: <https://www.unb.ca/cic/datasets/ids-2017.html>

3. CSE-CIC-IDS2018 dataset. Official page:
   <https://www.unb.ca/cic/datasets/ids-2018.html>

## Core anomaly-detection methods

4. Fei Tony Liu, Kai Ming Ting, and Zhi-Hua Zhou. *Isolation Forest.*
   2008 IEEE International Conference on Data Mining.
   <https://ieeexplore.ieee.org/document/4781136>

5. Markus M. Breunig, Hans-Peter Kriegel, Raymond T. Ng, and Jörg Sander.
   *LOF: Identifying Density-Based Local Outliers.* ACM SIGMOD 2000.
   <https://dl.acm.org/doi/10.1145/335191.335388>

6. Bernhard Schölkopf, John C. Platt, John Shawe-Taylor, Alex J. Smola, and
   Robert C. Williamson. *Estimating the Support of a High-Dimensional
   Distribution.* Neural Computation, 2001.
   <https://doi.org/10.1162/089976601750264965>

## Dataset-quality context

7. Patrik Goldschmidt and Daniela Chud�. *Network Intrusion Datasets: A Survey,
   Limitations, and Recommendations.* 2025.
   <https://arxiv.org/abs/2502.06688>

## Calibration / active-learning methodology

8. John Platt. *Probabilistic Outputs for Support Vector Machines and Comparisons to
   Regularized Likelihood Methods.* 1999.
   <https://doi.org/10.1007/978-94-011-5542-7_11>  (Platt scaling)

9. Bianca Zadrozny and Charles Elkan. *Transforming Classifier Scores into Accurate
   Multiclass Probability Estimates.* KDD 2002.
   <https://doi.org/10.1145/775047.775151>  (isotonic / binning calibration)

10. Alexandru Niculescu-Mizil and Rich Caruana. *Predicting Good Probabilities with
   Supervised Learning.* ICML 2005.
    <https://dl.acm.org/doi/10.1145/1102351.1102430>

11. Chuan Guo et al. *On Calibration of Modern Neural Networks.* ICML 2017.
    <https://arxiv.org/abs/1706.04599>  (expected-calibration-error framing)

12. David D. Lewis and William A. Gale. *A Sequential Algorithm for Training Text
    Classifiers.* SIGIR 1994.
    <https://doi.org/10.1007/978-1-4471-2099-5_1>  (uncertainty sampling)

13. Burr Settles. *Active Learning Literature Survey.* University of Wisconsin-Madison,
    2009. <https://minds.wisconsin.edu/handle/1793/60660>

14. Dan Cohn, Zoubin Ghahramani, and Michael I. Jordan. *Active Learning with
    Statistical Models.* JAIR 1996. (expected-error / entropy-based selection)
    <https://doi.org/10.1613/jair.295>

15. Nicholas Roy and Andrew McCallum. *Toward Optimal Active Learning through
    Sampling Estimation of Error Reduction.* ICML 2001. (diversity /
    representativeness sampling)

16. Simon Tong and Daphne Koller. *Support Vector Machine Active Learning with
    Applications to Text Classification.* JMLR 2001. (margin-based querying)

## Noise-related / imbalanced-learning context

17. Maarten Van Hulse, Taghi Khoshgoftaar, et al. *Data Sampling for Imbalance
    Learning.* 2019. (class-imbalance sampling and operating-point metrics)

18. Nitesh V. Chawla et al. *SMOTE: Synthetic Minority Over-sampling Technique.*
    JAIR 2002. <https://doi.org/10.1613/jair.953>

## AI-use note

AI coding assistance was used during implementation and drafting. The benchmark
selection, research questions, evaluation design, debugging decisions, result
interpretation, and final verification were carried out by Farooq Syed.
