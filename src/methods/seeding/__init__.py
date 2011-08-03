import nndsvd, random, fixed

methods = {"random": random.Random,
           "fixed": fixed.Fixed,
           "nndsvd": nndsvd.Nndsvd,
           "none": None }