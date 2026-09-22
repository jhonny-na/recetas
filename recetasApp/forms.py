from django import forms
from .models import Receta

class RecetaForm(forms.ModelForm):
    class Meta:
        model = Receta
        fields = ['nombre', 'categoria', 'chef', 'ingredientes', 'preparacion', 'imagen', 'imagen_url', 'tiempo_preparacion', 'porciones', 'dificultad']
        labels = {
            'chef': '¿Quién la preparó?',
            'imagen': 'Subir una foto',
            'imagen_url': 'O pegar el link de una foto',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'chef': forms.Select(attrs={'class': 'form-select'}),
            'ingredientes': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'preparacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'imagen': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'imagen_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'tiempo_preparacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 30 min'}),
            'porciones': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'dificultad': forms.Select(attrs={'class': 'form-select'}),
        }
