from .core import check, Report, Finding, Receipt, VERIFIED, DERIVED, MISMATCH, UNSUPPORTED
from .extract import extract, Claim
from .evidence import build as build_evidence, Evidence

__version__ = "0.1.0"
