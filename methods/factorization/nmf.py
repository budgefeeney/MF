
from models import *
from utils import *
from utils.linalg import *

class Nmf(nmf_std.Nmf_std):
    """
    Standard Nonnegative Matrix Factorization (NMF). Based on Kullbach-Leibler divergence, it uses simple multiplicative
    updates [2], enhanced to avoid numerical underflow [3]. Based on Euclidean distance, it uses simple multiplicative
    updates [2]. Different objective functions can be used, namely Euclidean distance, divergence or connectivity 
    matrix convergence. 
    
    Together with a novel model selection mechanism, NMF is an efficient method for identification of distinct molecular
    patterns and provides a powerful method for class discovery. It appears to have higher resolution such as HC or 
    SOM and to be less sensitive to a priori selection of genes. Rather than separating gene clusters based on distance
    computation, NMF detects context-dependent patterns of gene expression in complex biological systems. 
    
    Besides usages in bioinformatics NMF can be applied to text analysis, image processing, multiway clustering,
    environmetrics etc. 
    
    [2] Lee, D..D., and Seung, H.S., (2001). Algorithms for Non-negative Matrix Factorization, Adv. Neural Info. Proc. Syst. 13, 556-562.
    [3] Brunet, J.-P., Tamayo, P., Golub, T. R., Mesirov, J. P., (2004). Metagenes and molecular pattern discovery using matrix factorization. Proceedings of the National Academy of Sciences of the United States of America, 101(12), 4164-9. doi: 10.1073/pnas.0308531101.
    """

    def __init__(self, **params):
        """
        For detailed explanation of the general model parameters see :mod:`mf`.
        
        The following are algorithm specific model options which can be passed with values as keyword arguments.
        
        :param update: Type of update equations used in factorization. When specifying model parameter :param:`update` 
                       can be assigned to:
                           #. 'Euclidean' for classic Euclidean distance update equations, 
                           #. 'divergence' for divergence update equations.
                       By default Euclidean update equations are used. 
        :type update: `str`
        :param objective: Type of objective function used in factorization. When specifying model parameter :param:`objective`
                          can be assigned to:
                              #. 'fro' for standard Frobenius distance cost function,
                              #. 'div' for divergence of target matrix from NMF estimate cost function (KL),
                              #. 'conn' for connectivity matrix changed elements cost function. 
                          By default the standard Frobenius distance cost function is used.  
        :type objective: `str` 
        """
        self.name = "nmf"
        self.aseeds = ["random", "fixed", "nndsvd", "random_c", "random_vcol"]
        nmf_std.Nmf_std.__init__(self, params)
        
    def factorize(self):
        """
        Compute matrix factorization.
         
        Return fitted factorization model.
        """
        self._set_params()
                
        for _ in xrange(self.n_run):
            self.W, self.H = self.seed.initialize(self.V, self.rank, self.options)
            pobj = cobj = self.objective()
            iter = 0
            while self._is_satisfied(pobj, cobj, iter):
                pobj = cobj
                self.update()
                self._adjustment()
                cobj = self.objective() if not self.test_conv or iter % self.test_conv == 0 else cobj
                iter += 1
                if self.track_error:
                    self.tracker._track_error(self.residuals())
            if self.callback:
                self.final_obj = cobj
                mffit = mf_fit.Mf_fit(self) 
                self.callback(mffit)
            if self.track_factor:
                self.tracker._track_factor(W = self.W.copy(), H = self.H.copy())
        
        self.n_iter = iter 
        self.final_obj = cobj
        mffit = mf_fit.Mf_fit(self)
        return mffit
    
    def _is_satisfied(self, p_obj, c_obj, iter):
        """
        Compute the satisfiability of the stopping criteria based on stopping parameters and objective function value.
        
        :param p_obj: Objective function value from previous iteration. 
        :type p_obj: `float`
        :param c_obj: Current objective function value.
        :type c_obj: `float`
        :param iter: Current iteration number. 
        :type iter: `int`
        """
        if self.test_conv and iter % self.test_conv != 0:
            return True
        if self.max_iter and self.max_iter <= iter:
            return False
        if self.min_residuals and iter > 0 and c_obj - p_obj <= self.min_residuals:
            return False
        if iter > 0 and c_obj > p_obj:
            return False
        return True
    
    def _adjustment(self):
        """Adjust small values to factors to avoid numerical underflow."""
        self.H = max(self.H, np.finfo(self.H.dtype).eps)
        self.W = max(self.W, np.finfo(self.W.dtype).eps)
        
    def _set_params(self):
        """Set algorithm specific model options."""
        self.update = getattr(self, self.options.get('update', 'euclidean') + '_update') 
        self.objective = getattr(self, self.options.get('objective', 'fro') + '_objective')
        self.track_factor = self.options.get('track_factor', False)
        self.track_error = self.options.get('track_error', False)
        self.tracker = mf_track.Mf_track() if self.track_factor and self.n_run > 1 or self.track_error else None
        
    def euclidean_update(self):
        """Update basis and mixture matrix based on Euclidean distance multiplicative update rules."""
        self.H = multiply(self.H, elop(dot(self.W.T, self.V), dot(self.W.T, dot(self.W, self.H)), div))
        self.W = multiply(self.W , elop(dot(self.V, self.H.T), dot(self.W, dot(self.H, self.H.T)), div))
        
    def divergence_update(self):
        """Update basis and mixture matrix based on divergence multiplicative update rules."""
        H1 = repmat(self.W.sum(0).T, 1, self.V.shape[1])
        self.H = multiply(self.H, elop(dot(self.W.T, elop(self.V, dot(self.W, self.H), div)), H1, div))
        W1 = repmat(self.H.sum(1).T, self.V.shape[0], 1)
        self.W = multiply(self.W, elop(dot(elop(self.V, dot(self.W, self.H), div), self.H.T), W1, div))
        
    def fro_objective(self):
        """Compute squared Frobenius norm of a target matrix and its NMF estimate.""" 
        return (sop(self.V - dot(self.W, self.H), 2, pow)).sum()
    
    def div_objective(self):
        """Compute divergence of target matrix from its NMF estimate."""
        Va = dot(self.W, self.H)
        return (multiply(self.V, sop(elop(self.V, Va, div), op = log)) - self.V + Va).sum()
    
    def conn_objective(self):
        """
        Compute connectivity matrix changes -- number of changing elements.
        if the number of instances changing the cluster is lower or equal to min_residuals, terminate factorization run.
        """
        _, idx = argmax(self.H, axis = 0)
        mat1 = repmat(idx, self.V.shape[1], 1)
        mat2 = repmat(idx.T, 1, self.V.shape[1])
        cons = elop(mat1, mat2, eq)
        if not hasattr(self, 'consold'):
            self.consold = np.ones_like(self.cons) - cons
            self.cons = cons
        else:
            self.consold = self.cons
            self.cons = cons
        return elop(self.cons, self.consold, ne).sum()
        
    def __str__(self):
        return self.name