# Embedding Model Experiments — July 18, 2026

## Goal
Fine-tune Qwen3-Embedding-0.6B for legal-domain search quality. The base model is already good; we wanted "excellent."

## Attempts

### Attempt 1: functiongemma-270m hidden states (640 dims)
- **Approach:** Extract mean-pooled hidden states from the last layer of functiongemma-270m-it-8bit
- **Result:** Worked but was a hack. Not a purpose-built embedding model.
- **Verdict:** Replaced with Qwen3-Embedding.

### Attempt 2: Qwen3-Embedding-0.6B with LoRA (language modeling)
- **Command:** `mlx_lm.lora --model mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ --train --iters 500 --num-layers 12`
- **Training data:** 857 pairs formatted as Qwen chat template
- **Loss:** 4.288 → 1.061 (75% reduction)
- **Val loss:** 7.519 → 1.942 (74% reduction)
- **Trainable params:** 2.163M (0.36%)
- **Peak memory:** 4.94 GB
- **Time:** ~5 minutes
- **Result:** Adapter changed hidden states (MSE 1.24 vs base) but did NOT improve semantic similarity. Related queries scored only 1.19x higher than unrelated.
- **Root cause:** `mlx_lm.lora` trains on next-token prediction (language modeling), not contrastive embedding. The model learned to generate text, not to place similar documents closer in vector space.

### Attempt 3: Qwen3-Embedding-0.6B with projection head (contrastive)
- **Approach:** Train a 1024→256 dim MLP on top of frozen base model using InfoNCE loss with in-batch negatives
- **Training data:** 857 pairs, 1,481 unique texts
- **Loss:** 2.73 → 0.46 over 5 epochs (85% reduction)
- **Time:** ~3 minutes
- **Result:** Clean loss curve but top search results were wrong. "How do I file a motion" returned Bill Friedman Casino Design Pioneer as top result.
- **Root cause:** The projection head (656K params) is too small to capture legal-domain patterns. It's a linear remapping of the base model's output, not a true fine-tuning of the model's understanding.

### Attempt 4: Qwen3-Embedding-0.6B with LoRA (contrastive, custom training loop)
- **Approach:** Custom Python script applying LoRA to attention layers and training with InfoNCE loss
- **Result:** Failed — MLX's gradient tracking doesn't work with in-place weight modifications. The `nn.value_and_grad` function requires functional purity.
- **Root cause:** MLX's functional programming model doesn't support the pattern of "modify weights, compute, restore weights." The LoRA weights need to be applied as a differentiable transform, not as in-place assignments.

### Attempt 5: Qwen3-Embedding-0.6B with LoRA (language modeling, 800 iters, contrastive data)
- **Command:** `mlx_lm.lora --model ... --iters 800 --learning-rate 5e-5 --num-layers 16`
- **Training data:** 857 pairs formatted as Qwen chat template (same as Attempt 2 but more iters)
- **Loss:** 4.615 → 0.378 (92% reduction)
- **Time:** ~10 minutes
- **Result:** Same fundamental problem as Attempt 2 — language modeling loss doesn't improve embedding quality.

## Final Decision
**Use the base Qwen3-Embedding-0.6B model without any adapter.** The hybrid search (FTS5 for exact matches + base Qwen3 vectors for semantic) is the proven pattern from Cerebras, Anthropic, and every production RAG system.

## Key Technical Lessons

### MLX Array Storage
MLX uses bfloat16 internally. When converting to numpy for SQLite storage:
```python
# WRONG
emb_np = np.array(emb)  # tries to use MLX bfloat16 buffer directly

# RIGHT
emb_np = np.array(emb.astype(mx.float32))  # explicit float32 conversion
```

### FTS5 Query Sanitization
FTS5 treats `?` as a wildcard character. Always sanitize:
```python
sanitized = re.sub(r'[?.,!;:]+$', '', query)
sanitized = sanitized.replace('?', ' ')
```

### MLX Gradient Tracking
MLX uses functional programming for gradients. You cannot do in-place weight modifications and expect `value_and_grad` to work. The correct pattern is:
```python
def loss_fn(params, batch):
    # params is a dict of trainable weights
    # Use params to compute, don't modify global state
    return loss

loss_and_grad = nn.value_and_grad(loss_fn)
loss, grads = loss_and_grad(params, batch)
optimizer.update(params, grads)
```

### LoRA on Embedding Models
`mlx_lm.lora` trains on language modeling (next-token prediction). This is the WRONG loss function for embedding models. Embedding models need contrastive loss (InfoNCE, triplet, etc.) that pulls related texts together and pushes unrelated apart. There is no built-in MLX tool for contrastive LoRA training on embedding models.
