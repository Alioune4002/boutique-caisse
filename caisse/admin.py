from django.contrib import admin
from .models import Produit, Vente, Reassort


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prix', 'stock')  
    search_fields = ('nom',)  
    list_filter = ('prix',)  

@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = ('produit', 'quantite', 'total', 'date_vente')
    list_filter = ('date_vente',)  
    readonly_fields = ('total',)  
    
    
@admin.register(Reassort)
class ReassortAdmin(admin.ModelAdmin):
    list_display = ('produit', 'quantite_ajoutee', 'stock_avant', 'stock_apres', 'date_reassort')
    list_filter = ('date_reassort', 'produit')
    search_fields = ('produit__nom',)
    
