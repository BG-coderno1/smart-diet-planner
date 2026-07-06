"""
Fine-tunes a MobileNetV3-Small (pretrained on ImageNet) on your own labeled
food photos, so the app's photo-scanner recognizes specific dishes instead of
generic categories.

Requires: pip install torch torchvision pillow

Expected data layout (standard torchvision ImageFolder format) — one folder
per dish, using the exact same spelling as "Dish Name" in
Indian_Food_Nutrition_Processed.csv so predictions map straight onto the
nutrition database:

    data/food_images/
        masala dosa/
            img001.jpg
            img002.jpg
        paneer butter masala/
            img001.jpg
            ...
        idli/
            ...

A few dozen photos per class is enough to see real results; a few hundred
gives production-grade accuracy. Aim for varied lighting/plating/angles.

Usage:
    python train_food_classifier.py --data-dir data/food_images --epochs 15

Produces:
    model_weights/food_classifier.pt   (state dict, loaded by vision_deep.py)
    model_weights/labels.json          (class index -> dish name)
"""
import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", required=True, help="Path to ImageFolder-structured dataset")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--val-split", type=float, default=0.15)
    parser.add_argument("--output-dir", default="model_weights")
    args = parser.parse_args()

    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, random_split
        from torchvision import datasets
    except ImportError:
        sys.exit(
            "torch/torchvision are not installed.\n"
            "Install them first:  pip install torch torchvision\n"
            "(Not bundled by default because they are large and only needed for training.)"
        )

    from app.ml.vision_deep import build_model, IMAGE_SIZE  # noqa: E402

    if not os.path.isdir(args.data_dir):
        sys.exit(f"Data directory not found: {args.data_dir}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on {device}")

    # Use the same transforms the model was pretrained with, plus light
    # augmentation for training only.
    model, base_transforms = build_model(num_classes=1)  # temp; rebuilt below with real class count
    from torchvision import transforms as T

    train_transforms = T.Compose([
        T.RandomResizedCrop(IMAGE_SIZE, scale=(0.8, 1.0)),
        T.RandomHorizontalFlip(),
        T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    full_dataset = datasets.ImageFolder(args.data_dir, transform=train_transforms)
    num_classes = len(full_dataset.classes)
    if num_classes < 2:
        sys.exit("Need at least 2 dish classes (folders) to train a classifier.")

    val_size = max(1, int(len(full_dataset) * args.val_split))
    train_size = len(full_dataset) - val_size
    train_ds, val_ds = random_split(full_dataset, [train_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=2)

    model, _ = build_model(num_classes=num_classes)
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_acc = 0.0
    os.makedirs(args.output_dir, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)
        scheduler.step()

        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                preds = outputs.argmax(dim=1)
                correct += (preds == labels).sum().item()
                total += labels.size(0)
        val_acc = correct / max(total, 1)
        train_loss = running_loss / len(train_ds)
        print(f"Epoch {epoch}/{args.epochs}  train_loss={train_loss:.4f}  val_acc={val_acc:.3f}")

        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), os.path.join(args.output_dir, "food_classifier.pt"))
            with open(os.path.join(args.output_dir, "labels.json"), "w") as f:
                json.dump(full_dataset.classes, f, indent=2)

    print(f"Done. Best validation accuracy: {best_val_acc:.3f}")
    print(f"Saved to {args.output_dir}/food_classifier.pt")


if __name__ == "__main__":
    main()
