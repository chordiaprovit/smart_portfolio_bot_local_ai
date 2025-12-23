import 'package:flutter/material.dart';

class PillButton extends StatelessWidget {
  final String text;
  final bool selected;
  final VoidCallback onTap;

  const PillButton({super.key, required this.text, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      width: double.infinity,
      child: FilledButton(
        onPressed: onTap,
        style: FilledButton.styleFrom(
          backgroundColor: selected ? Theme.of(context).colorScheme.primary : Theme.of(context).colorScheme.surfaceVariant,
          foregroundColor: selected ? Theme.of(context).colorScheme.onPrimary : Theme.of(context).colorScheme.onSurfaceVariant,
          shape: const StadiumBorder(),
        ),
        child: Text(text, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
      ),
    );
  }
}
